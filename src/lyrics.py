"""Lyrics retrieval via LRCLIB with fallback to YouTube subtitle (VTT) parsing."""

import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional, List
import requests

logger = logging.getLogger(__name__)


@dataclass
class LyricsResult:
    synced_lyrics: Optional[str] = None
    plain_lyrics: Optional[str] = None
    source: str = "none"  # "lrclib", "youtube_subtitles", "none"


class LyricsManager:
    USER_AGENT = "MusicGetter/1.0.0 (https://github.com/escoba-inc/musicGetter)"

    @classmethod
    def fetch_from_lrclib(
        cls,
        title: str,
        artist: str,
        album: Optional[str] = None,
        duration: Optional[int] = None
    ) -> Optional[LyricsResult]:
        """Fetch synced or plain lyrics from open LRCLIB database."""
        base_url = "https://lrclib.net/api/get"
        params = {
            "track_name": title,
            "artist_name": artist,
        }
        if album and album.lower() != "singles":
            params["album_name"] = album
        if duration:
            params["duration"] = duration

        try:
            resp = requests.get(
                base_url,
                params=params,
                headers={"User-Agent": cls.USER_AGENT},
                timeout=8
            )
            if resp.status_code == 200:
                data = resp.json()
                synced = data.get("syncedLyrics")
                plain = data.get("plainLyrics")
                if synced or plain:
                    return LyricsResult(
                        synced_lyrics=synced,
                        plain_lyrics=plain,
                        source="lrclib"
                    )

            # If exact match failed, try search endpoint
            search_url = "https://lrclib.net/api/search"
            q = f"{artist} {title}"
            search_resp = requests.get(
                search_url,
                params={"q": q},
                headers={"User-Agent": cls.USER_AGENT},
                timeout=8
            )
            if search_resp.status_code == 200:
                results = search_resp.json()
                if results and isinstance(results, list):
                    first = results[0]
                    synced = first.get("syncedLyrics")
                    plain = first.get("plainLyrics")
                    if synced or plain:
                        return LyricsResult(
                            synced_lyrics=synced,
                            plain_lyrics=plain,
                            source="lrclib"
                        )

        except Exception as e:
            logger.debug(f"LRCLIB request failed for {artist} - {title}: {e}")

        return None

    @classmethod
    def _vtt_timestamp_to_lrc(cls, ts: str) -> Optional[str]:
        """Convert VTT timestamp (hh:mm:ss.mmm or mm:ss.mmm) to LRC format ([mm:ss.xx])."""
        parts = ts.strip().split(":")
        try:
            if len(parts) == 3:
                h, m, s = parts
                total_min = int(h) * 60 + int(m)
                sec, ms = s.split(".")
                return f"[{total_min:02d}:{int(sec):02d}.{ms[:2]}]"
            elif len(parts) == 2:
                m, s = parts
                sec, ms = s.split(".")
                return f"[{int(m):02d}:{int(sec):02d}.{ms[:2]}]"
        except (ValueError, IndexError):
            return None
        return None

    @classmethod
    def parse_vtt_to_lrc(cls, vtt_content: str) -> Optional[LyricsResult]:
        """Convert WebVTT subtitles into standard synchronized LRC format."""
        if not vtt_content or "WEBVTT" not in vtt_content:
            return None

        cue_re = re.compile(r"(\d{2}:\d{2}(?::\d{2})?\.\d{3})\s*-->\s*\d{2}:\d{2}(?::\d{2})?\.\d{3}")
        blocks = vtt_content.split("\n\n")

        lrc_lines: List[str] = []
        plain_lines: List[str] = []
        last_clean_text = ""

        for block in blocks:
            lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
            if not lines:
                continue

            cue_match = None
            text_lines = []
            for i, line in enumerate(lines):
                m = cue_re.search(line)
                if m:
                    cue_match = m
                    text_lines = lines[i + 1:]
                    break

            if cue_match and text_lines:
                ts = cls._vtt_timestamp_to_lrc(cue_match.group(1))
                if not ts:
                    continue

                raw_text = " ".join(text_lines)
                # Strip HTML/VTT tags like <c>, <c.color...>, </c>, <00:00:01.000>
                clean_text = re.sub(r"<[^>]+>", "", raw_text)
                # Strip non-speech tags: [Music], [Applause], (cheers)
                clean_text = re.sub(r"[\(\[\{](?:music|applause|cheers|laughter|singing|guitar\s+solo)[\)\]\}]", "", clean_text, flags=re.IGNORECASE)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                # Deduplicate rolling captions
                if clean_text and clean_text.lower() != last_clean_text.lower():
                    lrc_lines.append(f"{ts} {clean_text}")
                    plain_lines.append(clean_text)
                    last_clean_text = clean_text

        if not lrc_lines:
            return None

        synced = "\n".join(lrc_lines)
        plain = "\n".join(plain_lines)
        return LyricsResult(
            synced_lyrics=synced,
            plain_lyrics=plain,
            source="youtube_subtitles"
        )

    @classmethod
    def get_lyrics(
        cls,
        title: str,
        artist: str,
        album: Optional[str] = None,
        duration: Optional[int] = None,
        vtt_subtitle_path: Optional[str] = None,
        use_lrclib: bool = True,
        use_yt_subs: bool = True
    ) -> LyricsResult:
        """
        Orchestrate lyrics retrieval:
        1. Query LRCLIB if enabled
        2. Fallback to YouTube VTT subtitle if LRCLIB returns nothing and VTT is available
        """
        if use_lrclib:
            lrclib_res = cls.fetch_from_lrclib(title, artist, album, duration)
            if lrclib_res and (lrclib_res.synced_lyrics or lrclib_res.plain_lyrics):
                return lrclib_res

        if use_yt_subs and vtt_subtitle_path and os.path.exists(vtt_subtitle_path):
            try:
                with open(vtt_subtitle_path, "r", encoding="utf-8", errors="ignore") as f:
                    vtt_content = f.read()
                sub_res = cls.parse_vtt_to_lrc(vtt_content)
                if sub_res and sub_res.synced_lyrics:
                    return sub_res
            except Exception as e:
                logger.warning(f"Error parsing subtitle file {vtt_subtitle_path}: {e}")

        return LyricsResult()

    @classmethod
    def save_lrc_file(cls, audio_file_path: str, synced_lyrics: str) -> Optional[str]:
        """Save synchronized lyrics as a .lrc sidecar file next to the audio file."""
        if not synced_lyrics:
            return None
        base, _ = os.path.splitext(audio_file_path)
        lrc_path = f"{base}.lrc"
        try:
            with open(lrc_path, "w", encoding="utf-8") as f:
                f.write(synced_lyrics.strip() + "\n")
            return lrc_path
        except Exception as e:
            logger.warning(f"Failed to write sidecar .lrc file at {lrc_path}: {e}")
            return None
