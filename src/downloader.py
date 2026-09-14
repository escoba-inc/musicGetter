"""YouTube and YouTube Music downloader wrapping yt-dlp."""

import logging
import os
import glob
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import requests

logger = logging.getLogger(__name__)

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    logger.warning("yt-dlp is not installed in the current environment.")


def select_best_subtitle_file(
    track_temp_dir: str,
    youtube_id: str,
    preferred_languages: Optional[List[str]] = None,
    detected_language: Optional[str] = None
) -> Optional[str]:
    """
    Select the best subtitle file (.vtt) from candidate files matching detected language,
    audio original (-orig), and preferred language order.
    Discards unwanted languages (e.g. German machine translations for Spanish songs).
    """
    candidates = glob.glob(os.path.join(track_temp_dir, f"{youtube_id}*.vtt"))
    if not candidates:
        return None

    # Construct dynamic priority list
    priorities: List[str] = []
    if detected_language and detected_language != "unknown":
        priorities.append(f"{detected_language}.*")
        priorities.append(f"{detected_language}-orig")

    # YouTube's detected original audio speech recognition track
    priorities.append(".*-orig")

    if preferred_languages:
        for p in preferred_languages:
            if p not in priorities:
                priorities.append(p)
    else:
        for p in ["es.*", "en.*"]:
            if p not in priorities:
                priorities.append(p)

    scored_candidates = []
    for filepath in candidates:
        filename = os.path.basename(filepath)
        middle = filename[len(youtube_id):]
        if middle.startswith("."):
            middle = middle[1:]
        if middle.endswith(".vtt"):
            lang_code = middle[:-4]
        else:
            lang_code = middle

        matched_idx = None
        for idx, pref in enumerate(priorities):
            clean_pref = pref.strip()
            if clean_pref.lower() == "all":
                matched_idx = idx
                break
            try:
                if re.fullmatch(clean_pref, lang_code, flags=re.IGNORECASE) or re.match(clean_pref, lang_code, flags=re.IGNORECASE):
                    matched_idx = idx
                    break
            except re.error:
                if clean_pref.lower() in lang_code.lower():
                    matched_idx = idx
                    break

        if matched_idx is not None:
            scored_candidates.append((matched_idx, filepath))

    if scored_candidates:
        scored_candidates.sort(key=lambda x: x[0])
        return scored_candidates[0][1]

    return None


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
    channel_url: Optional[str] = None


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

        sub_langs = [s.strip() for s in (subtitle_languages or "es.*,en.*").split(",") if s.strip()]

        opts = self._get_base_ydl_opts()
        opts.update({
            "outtmpl": outtmpl,
            "writethumbnail": True,
            "writesubtitles": download_subs,
            "writeautomaticsub": download_subs,
            "subtitleslangs": sub_langs,
            "subtitlesformat": "vtt",
            "noplaylist": True,
            "extractor_args": {
                "youtube": {
                    "skip": ["translated_subs"]
                }
            },
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

                # Locate subtitle file matching preferred languages and detected language
                raw_title = info.get("title", "")
                channel = info.get("uploader") or info.get("channel", "")
                channel_url = info.get("channel_url") or info.get("uploader_url")

                from src.lyrics import detect_language
                detected_lang = detect_language(raw_title, channel)

                sub_path = select_best_subtitle_file(
                    track_temp_dir,
                    youtube_id,
                    sub_langs,
                    detected_language=detected_lang
                )

                return DownloadedTrack(
                    youtube_id=youtube_id,
                    audio_path=expected_audio,
                    thumbnail_path=thumb_path,
                    subtitle_path=sub_path,
                    duration=info.get("duration"),
                    raw_title=raw_title,
                    channel=channel,
                    yt_track=info.get("track"),
                    yt_artist=info.get("artist"),
                    channel_url=channel_url
                )

        except Exception as e:
            logger.error(f"Error downloading track {youtube_id}: {e}")
            return None

    @classmethod
    def download_channel_avatar(cls, channel_url: str) -> Optional[bytes]:
        """Download high-resolution avatar image for a YouTube channel."""
        if not channel_url:
            return None
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
            }
            resp = requests.get(channel_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', resp.text)
                if not m:
                    m = re.search(r'<link\s+rel=["\']image_src["\']\s+href=["\']([^"\']+)["\']', resp.text)
                if m:
                    avatar_url = m.group(1)
                    hi_res_url = re.sub(r"=s\d+(-c-k.*)?", "=s800-c-k-c0x00ffffff-no-rj", avatar_url)
                    try:
                        img_resp = requests.get(hi_res_url, headers=headers, timeout=10)
                        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                            return img_resp.content
                    except Exception:
                        pass
                    img_resp = requests.get(avatar_url, headers=headers, timeout=10)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        return img_resp.content
        except Exception as e:
            logger.warning(f"Failed to scrape channel avatar from {channel_url}: {e}")

        if YT_DLP_AVAILABLE:
            try:
                ydl_opts = {
                    "skip_download": True,
                    "quiet": True,
                    "no_warnings": True,
                    "playlist_items": "0",
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(channel_url, download=False)
                    thumbnails = info.get("thumbnails", [])
                    if thumbnails:
                        avatar_url = thumbnails[-1].get("url")
                        if avatar_url:
                            img_resp = requests.get(avatar_url, timeout=10)
                            if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                                return img_resp.content
            except Exception as e:
                logger.debug(f"yt-dlp channel avatar extraction failed for {channel_url}: {e}")

        return None
