"""YouTube and YouTube Music downloader wrapping yt-dlp."""

import logging
import os
import glob
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    logger.warning("yt-dlp is not installed in the current environment.")


@dataclass
class PlaylistInfo:
    playlist_id: str
    title: str
    entries: List[Dict[str, Any]]


@dataclass
class DownloadedTrack:
    youtube_id: str
    audio_path: str
    thumbnail_path: Optional[str] = None
    subtitle_path: Optional[str] = None
    duration: Optional[int] = None
    raw_title: str = ""
    channel: str = ""
    yt_track: Optional[str] = None
    yt_artist: Optional[str] = None


class Downloader:
    def __init__(self, cookies_file: Optional[str] = None):
        self.cookies_file = cookies_file if cookies_file and os.path.exists(cookies_file) else None

    def _get_base_ydl_opts(self) -> Dict[str, Any]:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "retries": 5,
            "fragment_retries": 5,
        }
        if self.cookies_file:
            opts["cookiefile"] = self.cookies_file
        return opts

    def get_playlist_info(self, playlist_url: str) -> Optional[PlaylistInfo]:
        """Extract playlist metadata and track list without downloading media."""
        if not YT_DLP_AVAILABLE:
            raise RuntimeError("yt-dlp is required to extract playlist info.")

        opts = self._get_base_ydl_opts()
        opts.update({
            "extract_flat": True,
            "skip_download": True,
        })

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                if not info:
                    return None

                playlist_id = info.get("id") or "unknown_playlist"
                playlist_title = info.get("title") or "YouTube Playlist"
                raw_entries = info.get("entries") or []

                clean_entries = []
                for entry in raw_entries:
                    if not entry:
                        continue
                    entry_id = entry.get("id")
                    if not entry_id:
                        continue
                    title = entry.get("title", "")
                    if title.lower() in [
                        "[private video]", "[deleted video]",
                        "private video", "deleted video",
                        "[unavailable video]", "unavailable video"
                    ]:
                        continue
                    clean_entries.append({
                        "id": entry_id,
                        "title": title,
                        "channel": entry.get("uploader") or entry.get("channel", ""),
                        "duration": entry.get("duration"),
                    })

                return PlaylistInfo(
                    playlist_id=playlist_id,
                    title=playlist_title,
                    entries=clean_entries
                )
        except Exception as e:
            logger.error(f"Failed to fetch playlist info from {playlist_url}: {e}")
            return None

    def download_track(
        self,
        youtube_id: str,
        temp_dir: str,
        audio_format: str = "opus",
        download_subs: bool = True,
        subtitle_languages: Optional[str] = None
    ) -> Optional[DownloadedTrack]:
        """
        Download the best audio stream, highest quality thumbnail, and subtitles for a single video.
        """
        if not YT_DLP_AVAILABLE:
            raise RuntimeError("yt-dlp is required to download tracks.")

        track_temp_dir = os.path.join(temp_dir, youtube_id)
        os.makedirs(track_temp_dir, exist_ok=True)
        outtmpl = os.path.join(track_temp_dir, "%(id)s.%(ext)s")

        sub_langs = [s.strip() for s in (subtitle_languages or "en.*,es.*,all").split(",") if s.strip()]

        opts = self._get_base_ydl_opts()
        opts.update({
            "outtmpl": outtmpl,
            "writethumbnail": True,
            "writesubtitles": download_subs,
            "writeautomaticsub": download_subs,
            "subtitleslangs": sub_langs,
            "subtitlesformat": "vtt",
            "noplaylist": True,
        })

        # Configure audio format extraction
        if audio_format == "opus":
            opts["format"] = "bestaudio[ext=opus]/bestaudio[acodec=opus]/bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "opus"},
            ]
        elif audio_format == "m4a":
            opts["format"] = "bestaudio[ext=m4a]/bestaudio[acodec=mp4a.40.2]/bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "m4a"},
            ]
        elif audio_format == "mp3":
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"},
            ]
        else:
            opts["format"] = "bestaudio/best"

        url = f"https://www.youtube.com/watch?v={youtube_id}"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return None

                # Locate the downloaded audio file
                audio_ext = "opus" if audio_format == "opus" else ("m4a" if audio_format == "m4a" else "mp3")
                expected_audio = os.path.join(track_temp_dir, f"{youtube_id}.{audio_ext}")

                if not os.path.exists(expected_audio):
                    # Check for any audio file created in the dir
                    audio_candidates = glob.glob(os.path.join(track_temp_dir, f"{youtube_id}.*"))
                    audio_candidates = [f for f in audio_candidates if not f.endswith((".jpg", ".png", ".webp", ".vtt", ".srv3", ".ttml"))]
                    if audio_candidates:
                        expected_audio = audio_candidates[0]
                    else:
                        logger.error(f"Audio file was not produced for {youtube_id}")
                        return None

                # Locate thumbnail
                thumb_candidates = glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.jpg")) + \
                                   glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.jpeg")) + \
                                   glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.webp")) + \
                                   glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.png"))
                thumb_path = thumb_candidates[0] if thumb_candidates else None

                # Locate subtitle file
                sub_candidates = glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.vtt"))
                sub_path = sub_candidates[0] if sub_candidates else None

                return DownloadedTrack(
                    youtube_id=youtube_id,
                    audio_path=expected_audio,
                    thumbnail_path=thumb_path,
                    subtitle_path=sub_path,
                    duration=info.get("duration"),
                    raw_title=info.get("title", ""),
                    channel=info.get("uploader") or info.get("channel", ""),
                    yt_track=info.get("track"),
                    yt_artist=info.get("artist")
                )

        except Exception as e:
            logger.error(f"Error downloading track {youtube_id}: {e}")
            return None
