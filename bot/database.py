from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from .models import PlaylistTrack


class PlaylistRepository:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(owner_id, name),
                    FOREIGN KEY(owner_id) REFERENCES users(id)
                );

                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    video_id TEXT,
                    title TEXT,
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id),
                    UNIQUE(playlist_id, position)
                );
                """
            )

    def _ensure_user(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute("INSERT OR IGNORE INTO users(id) VALUES (?)", (user_id,))

    def create_playlist(self, user_id: int, name: str) -> bool:
        self._ensure_user(user_id)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO playlists(owner_id, name) VALUES (?, ?)",
                (user_id, name),
            )
            return cur.rowcount > 0

    def delete_playlist(self, user_id: int, name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM playlists WHERE owner_id = ? AND name = ?",
                (user_id, name),
            ).fetchone()
            if row is None:
                return False
            playlist_id = row["id"]
            conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
            conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
            return True

    def list_playlists(self, user_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT name FROM playlists WHERE owner_id = ? ORDER BY name",
                (user_id,),
            ).fetchall()
        return [row["name"] for row in rows]

    def _get_playlist_id(self, conn: sqlite3.Connection, user_id: int, name: str) -> Optional[int]:
        row = conn.execute(
            "SELECT id FROM playlists WHERE owner_id = ? AND name = ?",
            (user_id, name),
        ).fetchone()
        if row is None:
            return None
        return int(row["id"])

    def add_track(
        self, user_id: int, playlist_name: str, source: str, video_id: Optional[str], title: Optional[str]
    ) -> bool:
        with self._connect() as conn:
            playlist_id = self._get_playlist_id(conn, user_id, playlist_name)
            if playlist_id is None:
                return False
            row = conn.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 AS next_pos FROM playlist_tracks WHERE playlist_id = ?",
                (playlist_id,),
            ).fetchone()
            next_pos = int(row["next_pos"]) if row else 1
            conn.execute(
                """
                INSERT INTO playlist_tracks(playlist_id, position, source, video_id, title)
                VALUES (?, ?, ?, ?, ?)
                """,
                (playlist_id, next_pos, source, video_id, title),
            )
            return True

    def list_tracks(self, user_id: int, playlist_name: str) -> Optional[list[PlaylistTrack]]:
        with self._connect() as conn:
            playlist_id = self._get_playlist_id(conn, user_id, playlist_name)
            if playlist_id is None:
                return None
            rows = conn.execute(
                """
                SELECT position, source, video_id, title
                FROM playlist_tracks
                WHERE playlist_id = ?
                ORDER BY position
                """,
                (playlist_id,),
            ).fetchall()
        return [
            PlaylistTrack(
                position=int(row["position"]),
                source=row["source"],
                video_id=row["video_id"],
                title=row["title"],
            )
            for row in rows
        ]

    def remove_track(self, user_id: int, playlist_name: str, position: int) -> bool:
        with self._connect() as conn:
            playlist_id = self._get_playlist_id(conn, user_id, playlist_name)
            if playlist_id is None:
                return False

            deleted = conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND position = ?",
                (playlist_id, position),
            )
            if deleted.rowcount == 0:
                return False

            rows = conn.execute(
                """
                SELECT id FROM playlist_tracks
                WHERE playlist_id = ?
                ORDER BY position
                """,
                (playlist_id,),
            ).fetchall()
            for new_pos, row in enumerate(rows, start=1):
                conn.execute(
                    "UPDATE playlist_tracks SET position = ? WHERE id = ?",
                    (new_pos, int(row["id"])),
                )
            return True
