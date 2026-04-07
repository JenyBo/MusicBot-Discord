from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import aiohttp


@dataclass(frozen=True)
class YouTubeVideo:
    title: str
    url: str


class YouTubeDataApi:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def _get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
        params = {**params, "key": self.api_key}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                data = await resp.json()
                if resp.status != 200:
                    message = data.get("error", {}).get("message") if isinstance(data, dict) else None
                    raise RuntimeError(f"YouTube API error ({resp.status}): {message or data}")
                return data

    async def trending_music_vn(self, limit: int = 10) -> list[YouTubeVideo]:
        data = await self._get(
            "videos",
            {
                "part": "snippet",
                "chart": "mostPopular",
                "regionCode": "VN",
                "videoCategoryId": "10",
                "maxResults": str(limit),
            },
        )
        items = data.get("items", []) if isinstance(data, dict) else []
        out: list[YouTubeVideo] = []
        for it in items:
            vid = it.get("id")
            title = (it.get("snippet") or {}).get("title")
            if not vid or not title:
                continue
            out.append(YouTubeVideo(title=title, url=f"https://www.youtube.com/watch?v={vid}"))
        return out

    async def newest_music_vn(self, limit: int = 10) -> list[YouTubeVideo]:
        # Best-effort "newest": recent music-category videos, region VN.
        data = await self._get(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "order": "date",
                "regionCode": "VN",
                "relevanceLanguage": "vi",
                "videoCategoryId": "10",
                "maxResults": str(limit),
            },
        )
        items = data.get("items", []) if isinstance(data, dict) else []
        out: list[YouTubeVideo] = []
        for it in items:
            vid = ((it.get("id") or {}) if isinstance(it, dict) else {}).get("videoId")
            title = (it.get("snippet") or {}).get("title")
            if not vid or not title:
                continue
            out.append(YouTubeVideo(title=title, url=f"https://www.youtube.com/watch?v={vid}"))
        return out

