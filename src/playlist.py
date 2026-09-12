"""Navidrome-compatible M3U8 playlist generator with relative file paths."""

import logging
import os
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """Sanitize string for safe filesystem usage across Linux, Windows, and macOS."""
    # Replace illegal path characters with hyphen or space
    cleaned = re.sub(r'[\\/*?:"<>|]', "-", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "Playlist"


class PlaylistGenerator:
    @classmethod
    def generate_m3u8(
        cls,
        playlist_name: str,
        tracks: List[Dict[str, Any]],
        playlists_dir: str
    ) -> str:
        """
        Generate an .m3u8 playlist file containing relative paths to audio tracks.
        Navidrome scans this file and displays the playlist in the web UI / Subsonic apps.
        """
        os.makedirs(playlists_dir, exist_ok=True)
        filename = f"{sanitize_filename(playlist_name)}.m3u8"
        file_path = os.path.join(playlists_dir, filename)

        lines = ["#EXTM3U"]

        for track in tracks:
            audio_path = track.get("file_path")
            if not audio_path or not os.path.exists(audio_path):
                continue

            duration = track.get("duration", 0)
            artist = track.get("artist", "Unknown Artist")
            title = track.get("title", "Unknown Title")

            # Calculate relative path from the playlist folder to the track file
            rel_path = os.path.relpath(audio_path, start=playlists_dir)
            # Ensure forward slashes for cross-platform and container compatibility
            rel_path_posix = rel_path.replace("\\", "/")

            lines.append(f"#EXTINF:{duration},{artist} - {title}")
            lines.append(rel_path_posix)

        content = "\n".join(lines) + "\n"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Generated playlist file: {file_path} with {len(lines) // 2} tracks")
        return file_path
