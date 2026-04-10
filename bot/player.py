from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict, deque

import discord

from .models import Track

log = logging.getLogger(__name__)


FFMPEG_RECONNECT_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


class GuildPlayer:
    def __init__(self) -> None:
        self.queue: deque[Track] = deque()
        self.next_track = asyncio.Event()
        self.current: Track | None = None
        self.worker_task: asyncio.Task | None = None


class PlayerManager:
    def __init__(self, bot: discord.Client, ffmpeg_executable: str) -> None:
        self.bot = bot
        self.players: dict[int, GuildPlayer] = defaultdict(GuildPlayer)
        self.ffmpeg_executable = ffmpeg_executable or "ffmpeg"

    def get_player(self, guild_id: int) -> GuildPlayer:
        return self.players[guild_id]

    async def enqueue(self, guild: discord.Guild, track: Track) -> None:
        player = self.get_player(guild.id)
        player.queue.append(track)
        if player.worker_task is None or player.worker_task.done():
            player.worker_task = self.bot.loop.create_task(self._player_worker(guild))

    async def _player_worker(self, guild: discord.Guild) -> None:
        player = self.get_player(guild.id)
        while player.queue:
            track = player.queue.popleft()
            player.current = track
            player.next_track.clear()

            voice = guild.voice_client
            if voice is None:
                break

            # Stream URLs from yt-dlp already contain auth tokens in query
            # params, so custom HTTP headers are not needed and cause escaping
            # issues on Windows (shlex.split breaks on embedded newlines).
            before_options = FFMPEG_RECONNECT_BEFORE

            log.info("Playing %s", track.title)

            try:
                # Do not pass stderr=PIPE: discord.py treats it as None; stderr inherits.
                # Avoid reading stderr in `after` (runs on audio thread; pipe may be None).
                source = discord.FFmpegPCMAudio(
                    track.stream_url,
                    before_options=before_options,
                    options=FFMPEG_OPTIONS,
                    executable=self.ffmpeg_executable,
                )
                transformed = discord.PCMVolumeTransformer(source, volume=0.8)
            except Exception:
                log.exception("Failed to create audio source")
                self.bot.loop.call_soon_threadsafe(player.next_track.set)
                continue

            def _after_playback(err: Exception | None) -> None:
                if err:
                    log.error("[voice] playback error: %s", err)
                self.bot.loop.call_soon_threadsafe(player.next_track.set)

            try:
                voice.play(transformed, after=_after_playback)
                log.info("  voice.is_playing() = %s", voice.is_playing())
            except Exception:
                log.exception("voice.play() raised an exception")
                self.bot.loop.call_soon_threadsafe(player.next_track.set)
                continue
            await player.next_track.wait()

        player.current = None

    def skip(self, guild_id: int) -> bool:
        voice = self.bot.get_guild(guild_id).voice_client if self.bot.get_guild(guild_id) else None
        if voice and voice.is_playing():
            voice.stop()
            return True
        return False

    async def stop(self, guild_id: int) -> None:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        player = self.get_player(guild_id)
        player.queue.clear()
        player.current = None
        if guild.voice_client and guild.voice_client.is_connected():
            guild.voice_client.stop()
            await guild.voice_client.disconnect()

    def queue_snapshot(self, guild_id: int) -> tuple[Track | None, list[Track]]:
        player = self.get_player(guild_id)
        return player.current, list(player.queue)
