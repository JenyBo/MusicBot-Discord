from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..database import PlaylistRepository
from ..player import PlayerManager
from ..resolver import YouTubeResolver


class MusicCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        resolver: YouTubeResolver,
        player: PlayerManager,
        playlists: PlaylistRepository,
    ) -> None:
        self.bot = bot
        self.resolver = resolver
        self.player = player
        self.playlists = playlists

    async def _ensure_voice(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceClient]:
        if interaction.guild is None or interaction.user is None:
            return None

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or member.voice is None or member.voice.channel is None:
            await interaction.response.send_message(
                "Join a voice channel first.", ephemeral=True
            )
            return None

        channel = member.voice.channel
        if interaction.guild.voice_client is None:
            return await channel.connect()
        if interaction.guild.voice_client.channel != channel:
            await interaction.guild.voice_client.move_to(channel)
        return interaction.guild.voice_client

    @app_commands.command(name="play", description="Play a YouTube track by URL or search")
    @app_commands.describe(query_or_url="YouTube URL or search text")
    async def play(self, interaction: discord.Interaction, query_or_url: str) -> None:
        await interaction.response.defer(thinking=True)
        voice = await self._ensure_voice(interaction)
        if voice is None or interaction.guild is None or interaction.user is None:
            return

        track = await self.resolver.extract(query_or_url, interaction.user.id)
        if track is None:
            await interaction.followup.send("Could not resolve this track.")
            return

        await self.player.enqueue(interaction.guild, track)
        await interaction.followup.send(f"Queued: **{track.title}**")

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only command.", ephemeral=True)
            return
        skipped = self.player.skip(interaction.guild.id)
        await interaction.response.send_message("Skipped." if skipped else "Nothing is playing.")

    @app_commands.command(name="stop", description="Stop playback and disconnect")
    async def stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only command.", ephemeral=True)
            return
        await self.player.stop(interaction.guild.id)
        await interaction.response.send_message("Stopped and disconnected.")

    @app_commands.command(name="queue", description="Show current queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("Guild only command.", ephemeral=True)
            return
        current, queued = self.player.queue_snapshot(interaction.guild.id)
        lines = []
        if current:
            lines.append(f"Now: **{current.title}**")
        if queued:
            lines.extend([f"{idx}. {track.title}" for idx, track in enumerate(queued, start=1)])
        if not lines:
            lines = ["Queue is empty."]
        await interaction.response.send_message("\n".join(lines))

    plist = app_commands.Group(
        name="plist", description="Manage personal music playlists"
    )

    @plist.command(name="create", description="Create a personal playlist")
    async def plist_create(self, interaction: discord.Interaction, name: str) -> None:
        ok = self.playlists.create_playlist(interaction.user.id, name)
        msg = f"Created playlist `{name}`." if ok else f"Playlist `{name}` already exists."
        await interaction.response.send_message(msg, ephemeral=True)

    @plist.command(name="delete", description="Delete one of your playlists")
    async def plist_delete(self, interaction: discord.Interaction, name: str) -> None:
        ok = self.playlists.delete_playlist(interaction.user.id, name)
        msg = f"Deleted playlist `{name}`." if ok else f"Playlist `{name}` not found."
        await interaction.response.send_message(msg, ephemeral=True)

    @plist.command(name="list", description="List your playlists")
    async def plist_list(self, interaction: discord.Interaction) -> None:
        names = self.playlists.list_playlists(interaction.user.id)
        if not names:
            await interaction.response.send_message(
                "You do not have playlists yet.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "\n".join([f"- {name}" for name in names]), ephemeral=True
        )

    @plist.command(name="add", description="Add a track to your playlist")
    async def plist_add(self, interaction: discord.Interaction, name: str, query_or_url: str) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        track = await self.resolver.extract(query_or_url, interaction.user.id)
        if track is None:
            await interaction.followup.send("Could not resolve this track.")
            return
        ok = self.playlists.add_track(
            interaction.user.id,
            name,
            query_or_url,
            track.webpage_url,
            track.title,
        )
        if not ok:
            await interaction.followup.send(f"Playlist `{name}` not found.")
            return
        await interaction.followup.send(f"Added **{track.title}** to `{name}`.")

    @plist.command(name="remove", description="Remove a track by its index in playlist")
    async def plist_remove(self, interaction: discord.Interaction, name: str, index: int) -> None:
        ok = self.playlists.remove_track(interaction.user.id, name, index)
        msg = (
            f"Removed track #{index} from `{name}`."
            if ok
            else "Playlist not found or index invalid."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @plist.command(name="show", description="Show tracks in a playlist")
    async def plist_show(self, interaction: discord.Interaction, name: str) -> None:
        tracks = self.playlists.list_tracks(interaction.user.id, name)
        if tracks is None:
            await interaction.response.send_message(f"Playlist `{name}` not found.", ephemeral=True)
            return
        if not tracks:
            await interaction.response.send_message(f"Playlist `{name}` is empty.", ephemeral=True)
            return
        lines = [
            f"{track.position}. {track.title or '(unknown title)'}" for track in tracks[:30]
        ]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @plist.command(name="play", description="Queue all tracks from your playlist")
    async def plist_play(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        voice = await self._ensure_voice(interaction)
        if voice is None or interaction.guild is None or interaction.user is None:
            return

        tracks = self.playlists.list_tracks(interaction.user.id, name)
        if tracks is None:
            await interaction.followup.send(f"Playlist `{name}` not found.")
            return
        if not tracks:
            await interaction.followup.send(f"Playlist `{name}` is empty.")
            return

        added = 0
        for item in tracks:
            query = item.video_id or item.source
            track = await self.resolver.extract(query, interaction.user.id)
            if track is None:
                continue
            await self.player.enqueue(interaction.guild, track)
            added += 1
        await interaction.followup.send(f"Queued {added} track(s) from `{name}`.")


async def setup(
    bot: commands.Bot,
    resolver: YouTubeResolver,
    player: PlayerManager,
    playlists: PlaylistRepository,
) -> None:
    await bot.add_cog(MusicCog(bot, resolver, player, playlists))
