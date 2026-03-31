from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    discord_token: str
    db_path: str = "data/musicbot.db"
    ffmpeg_executable: str = "ffmpeg"


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it in your environment or .env file.")
    ffmpeg_executable = os.getenv("FFMPEG_EXECUTABLE", "ffmpeg").strip() or "ffmpeg"
    return Settings(discord_token=token, ffmpeg_executable=ffmpeg_executable)
