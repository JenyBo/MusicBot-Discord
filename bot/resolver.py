from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import yt_dlp

from .models import Track

_CACHE_TTL = 30 * 60  # 30 minutes


class _CacheEntry:
    __slots__ = ("data", "expires_at")

    def __init__(self, data: dict[str, Any], ttl: float) -> None:
        self.data = data
        self.expires_at = time.monotonic() + ttl


class YouTubeResolver:
    def __init__(self) -> None:
        self._ydl_opts = {
            "format": "bestaudio[ext=webm]/bestaudio/best",
            "noplaylist": True,
            "default_search": "ytsearch1",
            "quiet": True,
            "no_warnings": True,
        }
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
            data = cached
        else:
            data = await asyncio.to_thread(self._extract_sync, query)
            if data is not None:
                self._cache_put(query, data)

        if data is None:
            return None
        if "entries" in data:
            entries = data.get("entries", [])
            if not entries:
                return None
            data = entries[0]
        stream_url = data.get("url")
        webpage_url = data.get("webpage_url")
        title = data.get("title")
        if not stream_url or not webpage_url or not title:
            return None
        return Track(
            title=title,
            webpage_url=webpage_url,
            stream_url=stream_url,
            http_headers=data.get("http_headers") or None,
            duration=data.get("duration"),
            requested_by=requester_id,
        )
