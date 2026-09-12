"""SQLite database for track tracking, deduplication, and playlist mapping."""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Create tables and indexes if they do not already exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    youtube_id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT,
                    duration INTEGER,
                    format TEXT,
                    has_lyrics BOOLEAN DEFAULT 0,
                    downloaded_at TIMESTAMP NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    playlist_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    url TEXT NOT NULL,
                    last_synced TIMESTAMP NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id TEXT NOT NULL,
                    youtube_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY (playlist_id, youtube_id),
                    FOREIGN KEY (playlist_id) REFERENCES playlists (playlist_id) ON DELETE CASCADE,
                    FOREIGN KEY (youtube_id) REFERENCES tracks (youtube_id) ON DELETE CASCADE
                )
            """)

            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_playlist_tracks_pos ON playlist_tracks(playlist_id, position)")
            conn.commit()

    def is_downloaded(self, youtube_id: str) -> bool:
        """Check if video has already been downloaded and the file still exists."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM tracks WHERE youtube_id = ?", (youtube_id,))
            row = cursor.fetchone()
            if row:
                file_path = row["file_path"]
                if os.path.exists(file_path):
                    return True
                else:
                    # File was deleted on disk; clean up record so it can be re-downloaded
                    cursor.execute("DELETE FROM tracks WHERE youtube_id = ?", (youtube_id,))
                    conn.commit()
            return False

    def get_track(self, youtube_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve track metadata from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tracks WHERE youtube_id = ?", (youtube_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_track(
        self,
        youtube_id: str,
        file_path: str,
        title: str,
        artist: str,
        album: Optional[str] = None,
        duration: Optional[int] = None,
        format_name: Optional[str] = None,
        has_lyrics: bool = False
    ):
        """Insert or replace downloaded track entry."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO tracks (
                    youtube_id, file_path, title, artist, album, duration, format, has_lyrics, downloaded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                youtube_id,
                file_path,
                title,
                artist,
                album or "Singles",
                duration or 0,
                format_name or "opus",
                1 if has_lyrics else 0,
                datetime.utcnow().isoformat()
            ))
            conn.commit()

    def update_playlist(
        self,
        playlist_id: str,
        name: str,
        url: str,
        youtube_ids: List[str]
    ):
        """Record playlist information and track associations."""
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO playlists (playlist_id, name, url, last_synced)
                VALUES (?, ?, ?, ?)
            """, (playlist_id, name, url, now))

            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
            for pos, ytid in enumerate(youtube_ids):
                cursor.execute("""
                    INSERT OR IGNORE INTO playlist_tracks (playlist_id, youtube_id, position)
                    VALUES (?, ?, ?)
                """, (playlist_id, ytid, pos))
            conn.commit()

    def get_playlist_tracks(self, playlist_id: str) -> List[Dict[str, Any]]:
        """Retrieve ordered list of tracks belonging to a playlist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.*, pt.position
                FROM playlist_tracks pt
                JOIN tracks t ON pt.youtube_id = t.youtube_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position ASC
            """, (playlist_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_tracks(self) -> List[Dict[str, Any]]:
        """Retrieve all tracks in library."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tracks ORDER BY downloaded_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_orphan_tracks(self, active_playlist_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Return tracks that do not belong to any active playlist.
        If active_playlist_ids is empty, all tracks are considered orphans.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not active_playlist_ids:
                cursor.execute("SELECT * FROM tracks")
            else:
                placeholders = ",".join("?" for _ in active_playlist_ids)
                cursor.execute(f"""
                    SELECT * FROM tracks
                    WHERE youtube_id NOT IN (
                        SELECT youtube_id FROM playlist_tracks WHERE playlist_id IN ({placeholders})
                    )
                """, active_playlist_ids)
            return [dict(row) for row in cursor.fetchall()]

    def delete_track(self, youtube_id: str):
        """Remove track from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_tracks WHERE youtube_id = ?", (youtube_id,))
            cursor.execute("DELETE FROM tracks WHERE youtube_id = ?", (youtube_id,))
            conn.commit()

    def get_stale_playlists(self, active_playlist_ids: List[str]) -> List[Dict[str, Any]]:
        """Find playlists in database that are no longer in active configuration."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if not active_playlist_ids:
                cursor.execute("SELECT * FROM playlists")
            else:
                placeholders = ",".join("?" for _ in active_playlist_ids)
                cursor.execute(f"""
                    SELECT * FROM playlists WHERE playlist_id NOT IN ({placeholders})
                """, active_playlist_ids)
            return [dict(row) for row in cursor.fetchall()]

    def delete_playlist(self, playlist_id: str):
        """Delete playlist record and associations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
            cursor.execute("DELETE FROM playlists WHERE playlist_id = ?", (playlist_id,))
            conn.commit()
