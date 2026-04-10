from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
import time
from typing import Any, Optional

_log = logging.getLogger(__name__)

import yt_dlp

from .models import Track

_CACHE_TTL = 60 * 60  # 60 minutes

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_cookie_path(path_str: str) -> str:
    p = Path(path_str.strip())
    if not p.is_absolute():
        p = (_PROJECT_ROOT / p).resolve()
    return str(p)


def _usable_audio_url(fmt: dict[str, Any]) -> str | None:
    url = fmt.get("url")
    if not url or not isinstance(url, str):
        return None
    low = url.lower()
    if "storyboard" in low or "/sb/" in low:
        return None
    ext = (fmt.get("ext") or "").lower()
    if ext in ("jpg", "jpeg", "png", "webp", "gif"):
        return None
    acodec = (fmt.get("acodec") or "").lower()
    if acodec in ("", "none"):
        return None
    return url


def _pick_stream_url(data: dict[str, Any]) -> str | None:
    for fmt in data.get("requested_formats") or []:
        u = _usable_audio_url(fmt)
        if u:
            return u
    u = _usable_audio_url(data)
    if u:
        return u
    formats = data.get("formats") or []

    def sort_key(f: dict[str, Any]) -> tuple[int, float]:
        # Prefer higher audio bitrate; missing abr sorts last.
        abr = f.get("abr")
        return (1 if abr is not None else 0, float(abr or 0.0))

    for fmt in sorted(formats, key=sort_key, reverse=True):
        u = _usable_audio_url(fmt)
        if u:
            return u
    return None


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: dict[str, Any], ttl: float) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl


class YouTubeResolver:
    def __init__(self) -> None:
        raw_cookie = os.getenv("YTDLP_COOKIEFILE", "").strip() or None
        cookiefile = None
        if raw_cookie:
            resolved = _resolve_cookie_path(raw_cookie)
            if Path(resolved).is_file():
                cookiefile = resolved
            else:
                _log.warning(
                    "YTDLP_COOKIEFILE set but file not found: %s (resolved: %s)",
                    raw_cookie,
                    resolved,
                )
        cookie_b64 = os.getenv("YTDLP_COOKIE_B64", "").strip() or None
        if not cookiefile and cookie_b64:
            try:
                raw = base64.b64decode(cookie_b64.encode("utf-8"), validate=False)
                cookie_path = Path("/tmp/yt_cookies.txt")
                cookie_path.parent.mkdir(parents=True, exist_ok=True)
                cookie_path.write_bytes(raw)
                try:
                    os.chmod(cookie_path, 0o600)
                except Exception:
                    pass
                cookiefile = str(cookie_path)
            except Exception:
                cookiefile = None
        # YouTube needs EJS (yt-dlp-ejs) + a JS runtime. Default API params only enable deno;
        # many Windows hosts have Node but not Deno — include both.
        js_runtimes: dict[str, dict] = {"deno": {}, "node": {}}
        extra = os.getenv("YTDLP_JS_RUNTIMES", "").strip().lower()
        if extra:
            js_runtimes = {name.strip(): {} for name in extra.split(",") if name.strip()}
        self._ydl_opts = {
            "format": "bestaudio/best",
            "format_sort": ["acodec:opus", "acodec:aac"],
            "noplaylist": True,
            "default_search": "ytsearch1",
            "quiet": True,
            "no_warnings": False,
            "js_runtimes": js_runtimes,
        }
        _log.info(
            "YouTubeResolver init: cookiefile=%s, js_runtimes=%s",
            cookiefile or "(none)",
            list(js_runtimes.keys()),
        )
        if cookiefile:
            self._ydl_opts["cookiefile"] = cookiefile
        self._cache: dict[str, _CacheEntry] = {}

    def _extract_sync(self, query: str) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)

    def _cache_get(self, key: str) -> dict[str, Any] | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() > entry.expires_at:
            del self._cache[key]
            return None
        return entry.data

    def _cache_put(self, key: str, data: dict[str, Any]) -> None:
        now = time.monotonic()
        if len(self._cache) > 200:
            expired = [k for k, v in self._cache.items() if now > v.expires_at]
            for k in expired:
                del self._cache[k]
        self._cache[key] = _CacheEntry(data, _CACHE_TTL)

    async def extract(self, query: str, requester_id: int) -> Optional[Track]:
        cached = self._cache_get(query)
        if cached is not None:
            _log.info("[resolve] cache hit for %r", query)
            data = cached
        else:
            t0 = time.monotonic()
            try:
                data = await asyncio.to_thread(self._extract_sync, query)
            except yt_dlp.utils.DownloadError as e:
                elapsed = time.monotonic() - t0
                msg = str(e)
                _log.warning("[resolve] DownloadError after %.1fs for %r: %s", elapsed, query, msg[:300])
                lowered = msg.lower()
                if (
                    "not a bot" in lowered
                    or "sign in to confirm" in lowered
                    or ("confirm you" in lowered and "bot" in lowered)
                    or "cookies-from-browser" in lowered
                    or "cookiefile" in lowered and "youtube" in lowered
                ):
                    raise RuntimeError(
                        "YouTube đang chặn server này (yêu cầu xác minh 'không phải bot'). "
                        "Bạn cần cung cấp cookies cho yt-dlp (env `YTDLP_COOKIEFILE` hoặc `YTDLP_COOKIE_B64`) hoặc đổi host/IP."
                    ) from e
                short = " ".join(msg.split())
                if len(short) > 250:
                    short = short[:247] + "..."
                raise RuntimeError(f"yt-dlp download error: {short}") from e
            except yt_dlp.utils.ExtractorError as e:
                elapsed = time.monotonic() - t0
                msg = str(e)
                _log.warning("[resolve] ExtractorError after %.1fs for %r: %s", elapsed, query, msg[:300])
                lowered = msg.lower()
                if (
                    "not a bot" in lowered
                    or "sign in to confirm" in lowered
                    or "confirm you" in lowered and "bot" in lowered
                    or "cookies-from-browser" in lowered
                    or "cookiefile" in lowered and "youtube" in lowered
                ):
                    raise RuntimeError(
                        "YouTube đang chặn server này (yêu cầu xác minh 'không phải bot'). "
                        "Bạn cần cung cấp cookies cho yt-dlp (env `YTDLP_COOKIEFILE` hoặc `YTDLP_COOKIE_B64`) hoặc đổi host/IP."
                    ) from e
                short = " ".join(msg.split())
                if len(short) > 250:
                    short = short[:247] + "..."
                raise RuntimeError(f"yt-dlp error: {short}") from e
            except Exception as e:
                elapsed = time.monotonic() - t0
                _log.error(
                    "[resolve] Unexpected %s after %.1fs for %r: %s",
                    type(e).__name__, elapsed, query, e,
                    exc_info=True,
                )
                return None

            elapsed = time.monotonic() - t0
            _log.info("[resolve] yt-dlp returned in %.1fs for %r", elapsed, query)
            if data is not None:
                self._cache_put(query, data)

        if data is None:
            _log.warning("[resolve] yt-dlp returned None for %r", query)
            return None
        if "entries" in data:
            entries = data.get("entries", [])
            if not entries:
                _log.warning("[resolve] search returned 0 entries for %r", query)
                return None
            data = entries[0]

        n_formats = len(data.get("formats") or [])
        has_req_fmts = bool(data.get("requested_formats"))
        top_url = bool(data.get("url"))
        stream_url = _pick_stream_url(data)
        webpage_url = data.get("webpage_url")
        if not webpage_url and data.get("id"):
            webpage_url = f"https://www.youtube.com/watch?v={data['id']}"
        title = data.get("title")

        if not stream_url or not webpage_url or not title:
            _log.warning(
                "[resolve] Missing fields for %r — "
                "stream_url=%s, webpage_url=%s, title=%s, "
                "n_formats=%d, has_requested_formats=%s, has_top_url=%s",
                query,
                bool(stream_url), bool(webpage_url), bool(title),
                n_formats, has_req_fmts, top_url,
            )
            if not stream_url and n_formats > 0:
                sample = data["formats"][-1]
                _log.warning(
                    "[resolve] last format sample: ext=%s acodec=%s vcodec=%s url=%s",
                    sample.get("ext"), sample.get("acodec"), sample.get("vcodec"),
                    (sample.get("url") or "")[:80],
                )
            return None

        _log.info("[resolve] OK %r → %s (n_formats=%d)", query, title, n_formats)
        return Track(
            title=title,
            webpage_url=webpage_url,
            stream_url=stream_url,
            http_headers=data.get("http_headers") or None,
            duration=data.get("duration"),
            requested_by=requester_id,
        )
