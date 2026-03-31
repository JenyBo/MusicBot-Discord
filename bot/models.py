from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Track:
    title: str
    webpage_url: str
    stream_url: str
    http_headers: dict[str, str] | None
    duration: Optional[int]
    requested_by: int


@dataclass
class PlaylistTrack:
    position: int
    source: str
    video_id: Optional[str]
    title: Optional[str]
