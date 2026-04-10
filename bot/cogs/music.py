from __future__ import annotations

import asyncio
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..database import PlaylistRepository
from ..player import PlayerManager
from ..resolver import YouTubeResolver
from ..youtube_api import YouTubeDataApi


async def _playlist_name_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    cog = interaction.client.get_cog("MusicCog")
    if cog is None or interaction.user is None:
        return []
    names = cog.playlists.autocomplete_playlist_names(
        interaction.user.id,
        current,
        limit_recent=5,
        limit_search=25,
    )
    out: list[app_commands.Choice[str]] = []
    for n in names:
        # Discord limits autocomplete choice strings to 100 chars
        if len(n) > 100:
            continue
        out.append(app_commands.Choice(name=n, value=n))
    return out


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
        self.youtube = YouTubeDataApi(getattr(bot, "youtube_api_key", None) or "")

    async def _ensure_voice(
        self, interaction: discord.Interaction
    ) -> Optional[discord.VoiceClient]:
        if interaction.guild is None or interaction.user is None:
            return None

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if member is None or member.voice is None or member.voice.channel is None:
            await self._send(interaction, "Hãy vào voice channel trước.")
            return None

        channel = member.voice.channel
        if interaction.guild.voice_client is None:
            return await channel.connect(timeout=120.0, reconnect=True)
        if interaction.guild.voice_client.channel != channel:
            await interaction.guild.voice_client.move_to(channel, timeout=120.0)
        return interaction.guild.voice_client

    async def _send(
        self,
        interaction: discord.Interaction,
        content: str,
        *,
        delete_after: Optional[float] = 5,
        ephemeral: bool = False,
    ) -> None:
        # After `defer()`, only followups are valid — e.g. `/play` → `_ensure_voice` → `_send`.
        if interaction.response.is_done():
            msg = await interaction.followup.send(content, ephemeral=ephemeral, wait=True)
        else:
            await interaction.response.send_message(content, ephemeral=ephemeral)
            try:
                msg = await interaction.original_response()
            except discord.HTTPException:
                return
        if delete_after is None or ephemeral:
            return
        asyncio.create_task(self._delete_later(msg, delete_after))

    async def _followup(
        self,
        interaction: discord.Interaction,
        content: str,
        *,
        delete_after: Optional[float] = 5,
        ephemeral: bool = False,
    ) -> None:
        msg = await interaction.followup.send(content, ephemeral=ephemeral, wait=True)
        if delete_after is None or ephemeral:
            return
        asyncio.create_task(self._delete_later(msg, delete_after))

    @staticmethod
    async def _delete_later(message: discord.Message, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except Exception:
            # Ignore missing perms / already deleted / etc.
            return

    @app_commands.command(name="help", description="Hiển thị danh sách lệnh")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Danh sách lệnh",
            description="Các lệnh slash hiện có của bot.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Phát nhạc",
            value=(
                "- `/play <từ_khóa_hoặc_link>`: Phát/Thêm bài vào hàng chờ\n"
                "- `/trendingvn`: Top 10 nhạc thịnh hành YouTube VN\n"
                "- `/newmusicvn`: Top 10 nhạc mới (YouTube VN)\n"
                "- `/skip`: Bỏ qua bài hiện tại\n"
                "- `/stop`: Dừng phát và rời voice\n"
                "- `/queue`: Xem danh sách đang phát/hàng chờ"
            ),
            inline=False,
        )
        embed.add_field(
            name="Playlist cá nhân",
            value=(
                "- `/plist add <tên> <từ_khóa_hoặc_link>`: Thêm tối đa 5 bài (ngăn cách bằng dấu phẩy). "
                "Nếu playlist chưa có sẽ tự tạo\n"
                "- `/plist remove <tên> <index>`: Xoá tối đa 5 bài theo số thứ tự (ngăn cách bằng dấu phẩy)\n"
                "- `/plist rename <tên_cũ> <tên_mới>`: Đổi tên playlist\n"
                "- `/plist show <tên>`: Xem các bài trong playlist\n"
                "- `/plist play <tên>`: Phát tất cả bài trong playlist\n"
                "- `/plist list`: Xem danh sách playlist\n"
                "- `/plist delete <tên>`: Xoá playlist\n"
                "- `/plist create <tên>`: Tạo playlist (không bắt buộc, vì `/plist add` tự tạo)"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @app_commands.command(name="trendingvn", description="Top 10 nhạc thịnh hành YouTube Việt Nam")
    async def trendingvn(self, interaction: discord.Interaction) -> None:
        if not self.youtube.api_key:
            await self._send(
                interaction,
                "Thiếu `YOUTUBE_API_KEY`. Hãy tạo API key YouTube Data API v3 và set biến môi trường này.",
                delete_after=None,
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            items = await self.youtube.trending_music_vn(limit=10)
        except Exception as e:
            await self._followup(interaction, f"Lỗi YouTube API: {e}", delete_after=None)
            return
        if not items:
            await self._followup(interaction, "Không lấy được danh sách trending.", delete_after=None)
            return
        lines = ["Top 10 nhạc thịnh hành (YouTube VN):"]
        for i, v in enumerate(items, start=1):
            lines.append(f"{i}. {v.title}\n{v.url}")
        await self._followup(interaction, "\n".join(lines), delete_after=None)

    @app_commands.command(name="newmusicvn", description="Top 10 nhạc mới YouTube Việt Nam (mới đăng)")
    async def newmusicvn(self, interaction: discord.Interaction) -> None:
        if not self.youtube.api_key:
            await self._send(
                interaction,
                "Thiếu `YOUTUBE_API_KEY`. Hãy tạo API key YouTube Data API v3 và set biến môi trường này.",
                delete_after=None,
            )
            return
        await interaction.response.defer(thinking=True)
        try:
            items = await self.youtube.newest_music_vn(limit=10)
        except Exception as e:
            await self._followup(interaction, f"Lỗi YouTube API: {e}", delete_after=None)
            return
        if not items:
            await self._followup(interaction, "Không lấy được danh sách nhạc mới.", delete_after=None)
            return
        lines = ["Top 10 nhạc mới (YouTube VN, mới đăng):"]
        for i, v in enumerate(items, start=1):
            lines.append(f"{i}. {v.title}\n{v.url}")
        await self._followup(interaction, "\n".join(lines), delete_after=None)

    @app_commands.command(name="play", description="Play a YouTube track by URL or search")
    @app_commands.describe(query_or_url="YouTube URL or search text")
    async def play(self, interaction: discord.Interaction, query_or_url: str) -> None:
        await interaction.response.defer(thinking=True)
        voice = await self._ensure_voice(interaction)
        if voice is None or interaction.guild is None or interaction.user is None:
            return

        try:
            track = await self.resolver.extract(query_or_url, interaction.user.id)
        except RuntimeError as e:
            await self._followup(interaction, str(e))
            return
        if track is None:
            await self._followup(interaction, "Không thể tìm/resolve bài này.")
            return

        await self.player.enqueue(interaction.guild, track)
        await self._followup(interaction, f"Đã thêm vào hàng chờ: **{track.title}**")

    @app_commands.command(name="skip", description="Skip current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await self._send(interaction, "Lệnh này chỉ dùng trong server.")
            return
        skipped = self.player.skip(interaction.guild.id)
        await self._send(interaction, "Đã skip." if skipped else "Hiện không có bài nào đang phát.")

    @app_commands.command(name="stop", description="Stop playback and disconnect")
    async def stop(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await self._send(interaction, "Lệnh này chỉ dùng trong server.")
            return
        # Acknowledge within 3s; voice disconnect can be slow on cloud hosts.
        await interaction.response.defer(thinking=False)
        await self.player.stop(interaction.guild.id)
        await self._followup(interaction, "Đã dừng phát và rời voice.")

    @app_commands.command(name="queue", description="Show current queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            await self._send(interaction, "Lệnh này chỉ dùng trong server.")
            return
        current, queued = self.player.queue_snapshot(interaction.guild.id)
        lines = []
        if current:
            lines.append(f"Now: **{current.title}**")
        if queued:
            lines.extend([f"{idx}. {track.title}" for idx, track in enumerate(queued, start=1)])
        if not lines:
            lines = ["Queue is empty."]
        await self._send(interaction, "\n".join(lines))

    plist = app_commands.Group(
        name="plist", description="Manage personal music playlists"
    )

    @staticmethod
    def _split_csv_items(raw: str, *, max_items: int) -> list[str]:
        items = [part.strip() for part in raw.split(",")]
        items = [x for x in items if x]
        return items[:max_items]

    @staticmethod
    def _parse_csv_ints(raw: str, *, max_items: int) -> list[int]:
        out: list[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                out.append(int(part))
            except ValueError:
                continue
        # unique while preserving order
        deduped: list[int] = []
        seen: set[int] = set()
        for n in out:
            if n in seen:
                continue
            seen.add(n)
            deduped.append(n)
        return deduped[:max_items]

    @plist.command(name="create", description="Create a personal playlist")
    async def plist_create(self, interaction: discord.Interaction, name: str) -> None:
        ok = self.playlists.create_playlist(interaction.user.id, name)
        msg = f"Created playlist `{name}`." if ok else f"Playlist `{name}` already exists."
        await self._send(interaction, msg)

    @plist.command(name="delete", description="Delete one of your playlists")
    @app_commands.autocomplete(name=_playlist_name_autocomplete)
    async def plist_delete(self, interaction: discord.Interaction, name: str) -> None:
        ok = self.playlists.delete_playlist(interaction.user.id, name)
        msg = f"Deleted playlist `{name}`." if ok else f"Playlist `{name}` not found."
        await self._send(interaction, msg)

    @plist.command(name="list", description="List your playlists")
    async def plist_list(self, interaction: discord.Interaction) -> None:
        names = self.playlists.list_playlists(interaction.user.id)
        if not names:
            await self._send(interaction, "Bạn chưa có playlist nào.")
            return
        await self._send(interaction, "\n".join([f"- {name}" for name in names]))

    @plist.command(name="rename", description="Rename one of your playlists")
    @app_commands.autocomplete(old_name=_playlist_name_autocomplete)
    async def plist_rename(self, interaction: discord.Interaction, old_name: str, new_name: str) -> None:
        ok = self.playlists.rename_playlist(interaction.user.id, old_name, new_name)
        if ok:
            await self._send(interaction, f"Đã đổi tên playlist `{old_name}` -> `{new_name}`.")
        else:
            await self._send(interaction, "Không đổi tên được (playlist không tồn tại hoặc tên mới không hợp lệ).")

    @plist.command(
        name="add",
        description="Add up to 5 tracks (comma-separated) to your playlist (auto-create if missing)",
    )
    @app_commands.describe(
        name="Tên playlist (gõ hoặc chọn từ gợi ý 5 list mới nhất)",
        query_or_url="YouTube URL/search; add multiple by separating with commas",
    )
    @app_commands.autocomplete(name=_playlist_name_autocomplete)
    async def plist_add(self, interaction: discord.Interaction, name: str, query_or_url: str) -> None:
        await interaction.response.defer(thinking=True)

        queries = self._split_csv_items(query_or_url, max_items=5)
        if not queries:
            await self._followup(interaction, "Hãy nhập ít nhất 1 từ khoá hoặc link.")
            return

        # Auto-create playlist if missing.
        self.playlists.create_playlist(interaction.user.id, name)

        added_titles: list[str] = []
        failed: list[str] = []

        for q in queries:
            track = await self.resolver.extract(q, interaction.user.id)
            if track is None:
                failed.append(q)
                continue
            ok = self.playlists.add_track(
                interaction.user.id,
                name,
                q,
                track.webpage_url,
                track.title,
            )
            if ok:
                added_titles.append(track.title or "(unknown title)")
            else:
                failed.append(q)

        lines: list[str] = []
        if added_titles:
            lines.append(f"Added {len(added_titles)} track(s) to `{name}`:")
            lines.extend([f"- **{t}**" for t in added_titles])
        if failed:
            lines.append("Could not add:")
            lines.extend([f"- `{x}`" for x in failed])
        if not lines:
            lines.append("Không thêm được bài nào.")

        await self._followup(interaction, "\n".join(lines))

    @plist.command(name="remove", description="Remove a track by its index in playlist")
    @app_commands.describe(index="1-based index; remove multiple by separating with commas (max 5)")
    @app_commands.autocomplete(name=_playlist_name_autocomplete)
    async def plist_remove(self, interaction: discord.Interaction, name: str, index: str) -> None:
        indices = self._parse_csv_ints(index, max_items=5)
        if not indices:
            await self._send(interaction, "Nhập 1-5 số thứ tự hợp lệ (ngăn cách bằng dấu phẩy).")
            return

        tracks_before = self.playlists.list_tracks(interaction.user.id, name)
        if tracks_before is None:
            await self._send(interaction, f"Không tìm thấy playlist `{name}`.")
            return

        max_pos = tracks_before[-1].position if tracks_before else 0
        valid = [i for i in indices if 1 <= i <= max_pos]
        if not valid:
            await self._send(interaction, "Tất cả số thứ tự đều không hợp lệ.")
            return

        title_by_pos = {t.position: (t.title or "(unknown title)") for t in tracks_before}
        removed: list[tuple[int, str]] = []
        for pos in sorted(set(valid), reverse=True):
            if self.playlists.remove_track(interaction.user.id, name, pos):
                removed.append((pos, title_by_pos.get(pos, "(unknown title)")))

        tracks_after = self.playlists.list_tracks(interaction.user.id, name) or []
        lines: list[str] = []
        if removed:
            lines.append(f"Removed {len(removed)} track(s) from `{name}`:")
            for pos, title in sorted(removed):
                lines.append(f"- #{pos}: **{title}**")
        else:
            lines.append("Nothing was removed.")

        if not tracks_after:
            lines.append(f"`{name}` is now empty.")
        else:
            lines.append(f"`{name}` now has {len(tracks_after)} track(s):")
            for t in tracks_after[:30]:
                lines.append(f"{t.position}. {t.title or '(unknown title)'}")
            if len(tracks_after) > 30:
                lines.append(f"... and {len(tracks_after) - 30} more.")

        await self._send(interaction, "\n".join(lines), ephemeral=False, delete_after=5)

    @plist.command(name="show", description="Show tracks in a playlist")
    @app_commands.autocomplete(name=_playlist_name_autocomplete)
    async def plist_show(self, interaction: discord.Interaction, name: str) -> None:
        tracks = self.playlists.list_tracks(interaction.user.id, name)
        if tracks is None:
            await self._send(interaction, f"Không tìm thấy playlist `{name}`.")
            return
        if not tracks:
            await self._send(interaction, f"Playlist `{name}` đang trống.")
            return
        lines = [
            f"{track.position}. {track.title or '(unknown title)'}" for track in tracks[:30]
        ]
        await self._send(interaction, "\n".join(lines))

    @plist.command(name="play", description="Queue all tracks from your playlist")
    @app_commands.autocomplete(name=_playlist_name_autocomplete)
    async def plist_play(self, interaction: discord.Interaction, name: str) -> None:
        await interaction.response.defer(thinking=True)
        voice = await self._ensure_voice(interaction)
        if voice is None or interaction.guild is None or interaction.user is None:
            return

        tracks = self.playlists.list_tracks(interaction.user.id, name)
        if tracks is None:
            await self._followup(interaction, f"Không tìm thấy playlist `{name}`.")
            return
        if not tracks:
            await self._followup(interaction, f"Playlist `{name}` đang trống.")
            return

        queries = [(item.video_id or item.source) for item in tracks]
        try:
            resolve_tasks = [self.resolver.extract(q, interaction.user.id) for q in queries]
            resolved = await asyncio.gather(*resolve_tasks)
        except RuntimeError as e:
            await self._followup(interaction, str(e))
            return

        added = 0
        for track in resolved:
            if track is None:
                continue
            await self.player.enqueue(interaction.guild, track)
            added += 1

        await self._followup(interaction, f"Đã thêm {added} bài từ `{name}` vào hàng chờ.")


async def setup(
    bot: commands.Bot,
    resolver: YouTubeResolver,
    player: PlayerManager,
    playlists: PlaylistRepository,
) -> None:
    await bot.add_cog(MusicCog(bot, resolver, player, playlists))
