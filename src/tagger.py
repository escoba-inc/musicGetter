"""Audio metadata and artwork tagging using Mutagen for Opus, M4A, and MP3."""

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import mutagen
    from mutagen.oggopus import OggOpus
    from mutagen.mp4 import MP4, MP4Cover
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TDRC, TCON, USLT, APIC
    from mutagen.flac import Picture
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False
    logger.warning("Mutagen library is not installed in the current environment.")


class AudioTagger:
    @classmethod
    def apply_tags(
        cls,
        file_path: str,
        title: str,
        artist: str,
        album: Optional[str] = None,
        album_artist: Optional[str] = None,
        track_number: Optional[int] = None,
        year: Optional[int] = None,
        genre: Optional[str] = None,
        lyrics: Optional[str] = None,
        artwork_bytes: Optional[bytes] = None,
        artwork_mime: str = "image/jpeg"
    ) -> bool:
        """Apply audio metadata tags and cover art based on file extension."""
        if not MUTAGEN_AVAILABLE:
            logger.warning("Cannot tag file: Mutagen is not available.")
            return False

        if not os.path.exists(file_path):
            logger.error(f"Cannot tag non-existent file: {file_path}")
            return False

        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext in [".opus", ".ogg"]:
                return cls._tag_ogg_opus(
                    file_path, title, artist, album, album_artist,
                    track_number, year, genre, lyrics, artwork_bytes, artwork_mime
                )
            elif ext in [".m4a", ".mp4", ".aac"]:
                return cls._tag_mp4(
                    file_path, title, artist, album, album_artist,
                    track_number, year, genre, lyrics, artwork_bytes, artwork_mime
                )
            elif ext == ".mp3":
                return cls._tag_mp3(
                    file_path, title, artist, album, album_artist,
                    track_number, year, genre, lyrics, artwork_bytes, artwork_mime
                )
            else:
                logger.warning(f"Unsupported audio format for tagging: {ext}")
                return False
        except Exception as e:
            logger.error(f"Failed to tag {file_path}: {e}")
            return False

    @classmethod
    def _tag_ogg_opus(
        cls,
        file_path: str,
        title: str,
        artist: str,
        album: Optional[str],
        album_artist: Optional[str],
        track_number: Optional[int],
        year: Optional[int],
        genre: Optional[str],
        lyrics: Optional[str],
        artwork_bytes: Optional[bytes],
        artwork_mime: str
    ) -> bool:
        audio = OggOpus(file_path)
        audio["TITLE"] = title
        audio["ARTIST"] = artist
        if album:
            audio["ALBUM"] = album
        if album_artist:
            audio["ALBUMARTIST"] = album_artist
        if track_number is not None:
            audio["TRACKNUMBER"] = str(track_number)
        if year is not None:
            audio["DATE"] = str(year)
        if genre:
            audio["GENRE"] = genre
        if lyrics:
            audio["LYRICS"] = lyrics
            audio["UNSYNCEDLYRICS"] = lyrics

        if artwork_bytes:
            pic = Picture()
            pic.data = artwork_bytes
            pic.type = 3  # Cover (front)
            pic.mime = artwork_mime
            pic.desc = "Cover"
            pic.depth = 24
            try:
                import io
                from PIL import Image
                with Image.open(io.BytesIO(artwork_bytes)) as img:
                    pic.width, pic.height = img.size
            except Exception:
                pic.width = 0
                pic.height = 0
            audio["metadata_block_picture"] = [base64.b64encode(pic.write()).decode("ascii")]

        audio.save()
        logger.debug(f"Tagged Opus file: {file_path}")
        return True

    @classmethod
    def _tag_mp4(
        cls,
        file_path: str,
        title: str,
        artist: str,
        album: Optional[str],
        album_artist: Optional[str],
        track_number: Optional[int],
        year: Optional[int],
        genre: Optional[str],
        lyrics: Optional[str],
        artwork_bytes: Optional[bytes],
        artwork_mime: str
    ) -> bool:
        audio = MP4(file_path)
        audio["\xa9nam"] = [title]
        audio["\xa9ART"] = [artist]
        if album:
            audio["\xa9alb"] = [album]
        if album_artist:
            audio["aART"] = [album_artist]
        if track_number is not None:
            audio["trkn"] = [(track_number, 0)]
        if year is not None:
            audio["\xa9day"] = [str(year)]
        if genre:
            audio["\xa9gen"] = [genre]
        if lyrics:
            audio["\xa9lyr"] = [lyrics]

        if artwork_bytes:
            fmt = MP4Cover.FORMAT_PNG if "png" in artwork_mime.lower() else MP4Cover.FORMAT_JPEG
            audio["covr"] = [MP4Cover(artwork_bytes, imageformat=fmt)]

        audio.save()
        logger.debug(f"Tagged M4A file: {file_path}")
        return True

    @classmethod
    def _tag_mp3(
        cls,
        file_path: str,
        title: str,
        artist: str,
        album: Optional[str],
        album_artist: Optional[str],
        track_number: Optional[int],
        year: Optional[int],
        genre: Optional[str],
        lyrics: Optional[str],
        artwork_bytes: Optional[bytes],
        artwork_mime: str
    ) -> bool:
        try:
            audio = ID3(file_path)
        except Exception:
            audio = ID3()

        audio.add(TIT2(encoding=3, text=title))
        audio.add(TPE1(encoding=3, text=artist))
        if album:
            audio.add(TALB(encoding=3, text=album))
        if album_artist:
            audio.add(TPE2(encoding=3, text=album_artist))
        if track_number is not None:
            audio.add(TRCK(encoding=3, text=str(track_number)))
        if year is not None:
            audio.add(TDRC(encoding=3, text=str(year)))
        if genre:
            audio.add(TCON(encoding=3, text=genre))
        if lyrics:
            audio.add(USLT(encoding=3, lang="eng", desc="Lyrics", text=lyrics))

        if artwork_bytes:
            audio.add(APIC(
                encoding=3,
                mime=artwork_mime,
                type=3,  # Front cover
                desc="Cover",
                data=artwork_bytes
            ))

        audio.save(file_path)
        logger.debug(f"Tagged MP3 file: {file_path}")
        return True
