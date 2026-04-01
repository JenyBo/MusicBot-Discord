from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    discord_token: str
    db_path: str = "data/musicbot.db"
    ffmpeg_executable: str = "ffmpeg"
    dev_guild_id: int | None = None


def load_settings() -> Settings:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is missing. Set it in your environment or .env file.")
    ffmpeg_executable = os.getenv("FFMPEG_EXECUTABLE", "ffmpeg").strip() or "ffmpeg"
    raw_guild = os.getenv("DEV_GUILD_ID", "").strip()
    dev_guild_id = int(raw_guild) if raw_guild.isdigit() else None
    return Settings(discord_token=token, ffmpeg_executable=ffmpeg_executable, dev_guild_id=dev_guild_id)
