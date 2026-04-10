from __future__ import annotations

import logging
import os

from aiohttp import web
import discord
from discord import app_commands
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
        self.youtube_api_key = self.settings.youtube_api_key

    async def setup_hook(self) -> None:
        await setup_music_cog(self, self.resolver, self.player, self.playlists)

        @self.tree.error
        async def on_app_command_error(
            interaction: discord.Interaction,
            error: app_commands.AppCommandError,
        ) -> None:
            orig = error.__cause__ if isinstance(error, app_commands.CommandInvokeError) else None
            if isinstance(orig, discord.NotFound) and getattr(orig, "code", None) == 10062:
                logging.getLogger(__name__).warning(
                    "Interaction unknown/expired (10062) on command %r — Discord rejected the token. "
                    "Common on Render: free-tier sleep/cold start, CPU lag before defer(), or a second "
                    "process using the same bot token (e.g. local + cloud). Keep the service warm "
                    "(ping GET / or /health every few minutes) and run only one bot instance.",
                    getattr(interaction.command, "name", None),
                )
                return
            cmd = interaction.command
            log = logging.getLogger(__name__)
            if cmd is not None:
                if cmd._has_any_error_handlers():
                    return
                log.error("Ignoring exception in command %r", cmd.name, exc_info=error)
            else:
                log.error("Ignoring exception in command tree", exc_info=error)

        # If deployed as a Render "Web Service", bind a small health server to $PORT.
        port_raw = os.getenv("PORT", "").strip()
        if port_raw.isdigit():
            port = int(port_raw)
            app = web.Application()

            async def health(_req: web.Request) -> web.Response:
                return web.Response(text="ok")

            app.router.add_get("/health", health)
            app.router.add_get("/", health)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=port)
            await site.start()

        # Global sync can take a while to appear. For faster iteration, set DEV_GUILD_ID
        # to sync commands instantly to a specific server.
        if self.settings.dev_guild_id:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            return
        await self.tree.sync()


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    # Ensure opus encoder is loaded before any voice playback.
    if not discord.opus.is_loaded():
        discord.opus._load_default()
    if not discord.opus.is_loaded():
        raise RuntimeError(
            "Could not load libopus.\n"
            "- Linux (Debian/Ubuntu): install `libopus0` (and `ffmpeg`)\n"
            "- Windows: install Opus or place `opus.dll` in your PATH"
        )
    logging.info("Opus loaded: %s", discord.opus.is_loaded())

    bot = MusicBot()
    bot.run(bot.settings.discord_token)


if __name__ == "__main__":
    main()
