from __future__ import annotations

import asyncio
from typing import Any, Optional

import yt_dlp

from .models import Track


class YouTubeResolver:
    def __init__(self) -> None:
        self._ydl_opts = {
            "format": "bestaudio[ext=webm]/bestaudio/best",
            "noplaylist": True,
            "default_search": "ytsearch1",
            "quiet": True,
            "no_warnings": True,
        }

    def _extract_sync(self, query: str) -> dict[str, Any]:
        with yt_dlp.YoutubeDL(self._ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)

    async def extract(self, query: str, requester_id: int) -> Optional[Track]:
        data = await asyncio.to_thread(self._extract_sync, query)
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
