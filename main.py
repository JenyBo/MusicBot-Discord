from __future__ import annotations

import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.config import load_settings
from bot.database import PlaylistRepository
from bot.player import PlayerManager
from bot.resolver import YouTubeResolver
from bot.cogs.music import setup as setup_music_cog


class MusicBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.resolver = YouTubeResolver()
        self.settings = load_settings()
        self.playlists = PlaylistRepository(self.settings.db_path)
        self.player = PlayerManager(self, ffmpeg_executable=self.settings.ffmpeg_executable)

    async def setup_hook(self) -> None:
        await setup_music_cog(self, self.resolver, self.player, self.playlists)
        await self.tree.sync()


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    # Ensure opus encoder is loaded before any voice playback.
    if not discord.opus.is_loaded():
        discord.opus._load_default()
    if not discord.opus.is_loaded():
        raise RuntimeError(
            "Could not load libopus. Install it or place opus.dll in your PATH."
        )
    logging.info("Opus loaded: %s", discord.opus.is_loaded())

    bot = MusicBot()
    bot.run(bot.settings.discord_token)


if __name__ == "__main__":
    main()
