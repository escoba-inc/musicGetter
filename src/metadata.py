"""Metadata enrichment via iTunes Search API, Deezer API, and high-res cover art resolution."""

import io
import logging
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional, Tuple
from PIL import Image
import requests

from src.cleaner import CleanMetadata, TitleCleaner

logger = logging.getLogger(__name__)


@dataclass
class EnrichedMetadata:
    title: str
    artist: str
    album: str
    album_artist: str
    track_number: Optional[int] = None
    year: Optional[int] = None
    genre: Optional[str] = None
    artwork_bytes: Optional[bytes] = None
    artwork_mime: str = "image/jpeg"
    source: str = "youtube"  # "itunes", "deezer", or "youtube"
    artist_image_bytes: Optional[bytes] = None


class MetadataEnricher:
    USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @classmethod
    def _normalize_string(cls, s: str) -> str:
        """Strip punctuation and whitespace for fuzzy comparison."""
        return re.sub(r"[^\w\s]", "", s.lower()).strip()

    @classmethod
    def _similarity_score(cls, str1: str, str2: str) -> float:
        """Calculate simple token similarity ratio."""
        n1 = cls._normalize_string(str1)
        n2 = cls._normalize_string(str2)
        if n1 == n2:
            return 1.0
        if n1 in n2 or n2 in n1:
            return 0.8
        tokens1 = set(n1.split())
        tokens2 = set(n2.split())
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        return len(intersection) / max(len(tokens1), len(tokens2))

    @classmethod
    def query_itunes(
        cls,
        clean_meta: CleanMetadata,
        duration: Optional[int] = None,
        max_art_res: int = 3000
    ) -> Optional[EnrichedMetadata]:
        """Query iTunes Search API for canonical track info and pristine cover art."""
        search_term = f"{clean_meta.artist} {clean_meta.cleaned_title}"
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(search_term)}&entity=song&limit=5"

        try:
            resp = requests.get(url, headers={"User-Agent": cls.USER_AGENT}, timeout=8)
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("results", [])
            if not results:
                # Try search with title only
                url_title = f"https://itunes.apple.com/search?term={urllib.parse.quote(clean_meta.cleaned_title)}&entity=song&limit=5"
                resp = requests.get(url_title, headers={"User-Agent": cls.USER_AGENT}, timeout=8)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])

            best_match = None
            best_score = 0.0

            for item in results:
                track_name = item.get("trackName", "")
                artist_name = item.get("artistName", "")
                track_dur_ms = item.get("trackTimeMillis", 0)

                title_sim = cls._similarity_score(clean_meta.cleaned_title, track_name)
                artist_sim = cls._similarity_score(clean_meta.artist, artist_name)
                combined_score = (title_sim * 0.6) + (artist_sim * 0.4)

                # Duration bonus if duration is provided
                if duration and track_dur_ms:
                    dur_diff = abs((track_dur_ms / 1000.0) - duration)
                    if dur_diff <= 8.0:
                        combined_score += 0.2
                    elif dur_diff > 25.0:
                        combined_score -= 0.3

                if combined_score > best_score and combined_score >= 0.65:
                    best_score = combined_score
                    best_match = item

            if not best_match:
                return None

            # Extract release year
            release_date = best_match.get("releaseDate", "")
            year = None
            if release_date and len(release_date) >= 4:
                try:
                    year = int(release_date[:4])
                except ValueError:
                    pass

            # Download pristine artwork
            artwork_url = best_match.get("artworkUrl100", "")
            artwork_bytes = None
            if artwork_url:
                # Replace 100x100bb with high-resolution e.g. 3000x3000bb
                hi_res_url = re.sub(r"/\d+x\d+bb", f"/{max_art_res}x{max_art_res}bb", artwork_url)
                try:
                    art_resp = requests.get(hi_res_url, headers={"User-Agent": cls.USER_AGENT}, timeout=10)
                    if art_resp.status_code == 200 and len(art_resp.content) > 1000:
                        artwork_bytes = art_resp.content
                except Exception as e:
                    logger.debug(f"Failed to fetch iTunes hi-res artwork: {e}")

            itunes_artist = best_match.get("artistName", clean_meta.artist)
            primary_artist, extra_artists = TitleCleaner.extract_primary_artist(itunes_artist)
            track_title = best_match.get("trackName", clean_meta.cleaned_title)
            # Strip "- Single" or "(Single)" from track title if present
            track_title = re.sub(r"\s*[-–—]\s*Single$", "", track_title, flags=re.IGNORECASE).strip()
            track_title = re.sub(r"[\(\[\{]\s*Single\s*[\)\]\}]", "", track_title, flags=re.IGNORECASE).strip()
            if extra_artists and not re.search(r"[\(\[\{]\s*(?:feat|ft)\.?\s+", track_title, re.IGNORECASE):
                track_title = f"{track_title} (feat. {extra_artists})"

            itunes_album = best_match.get("collectionName", "Singles")
            # If the collection is a single (e.g. "Song - Single"), unify into "Singles"
            if re.search(r"(?:[-–—\(\[]\s*single\s*[\)\]]?|^single$)", itunes_album, re.IGNORECASE):
                album_name = "Singles"
            else:
                album_name = itunes_album

            return EnrichedMetadata(
                title=track_title,
                artist=primary_artist,
                album=album_name,
                album_artist=primary_artist,
                track_number=best_match.get("trackNumber"),
                year=year,
                genre=best_match.get("primaryGenreName"),
                artwork_bytes=artwork_bytes,
                artwork_mime="image/jpeg",
                source="itunes"
            )

        except Exception as e:
            logger.debug(f"iTunes search failed for '{search_term}': {e}")
            return None

    @classmethod
    def query_deezer(
        cls,
        clean_meta: CleanMetadata,
        duration: Optional[int] = None
    ) -> Optional[EnrichedMetadata]:
        """Fallback query to Deezer API for metadata and 1000x1000 cover."""
        search_term = f"{clean_meta.artist} {clean_meta.cleaned_title}"
        url = f"https://api.deezer.com/search?q={urllib.parse.quote(search_term)}&limit=5"

        try:
            resp = requests.get(url, headers={"User-Agent": cls.USER_AGENT}, timeout=8)
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("data", [])
            if not results:
                return None

            best_match = None
            best_score = 0.0

            for item in results:
                track_name = item.get("title", "")
                artist_info = item.get("artist", {})
                artist_name = artist_info.get("name", "") if isinstance(artist_info, dict) else ""
                track_dur = item.get("duration", 0)

                title_sim = cls._similarity_score(clean_meta.cleaned_title, track_name)
                artist_sim = cls._similarity_score(clean_meta.artist, artist_name)
                score = (title_sim * 0.6) + (artist_sim * 0.4)

                if duration and track_dur:
                    dur_diff = abs(track_dur - duration)
                    if dur_diff <= 8.0:
                        score += 0.2
                    elif dur_diff > 25.0:
                        score -= 0.3

                if score > best_score and score >= 0.65:
                    best_score = score
                    best_match = item

            if not best_match:
                return None

            album_info = best_match.get("album", {})
            album_title = album_info.get("title", "Singles") if isinstance(album_info, dict) else "Singles"
            art_url = album_info.get("cover_xl") or album_info.get("cover_big") if isinstance(album_info, dict) else None

            artwork_bytes = None
            if art_url:
                try:
                    art_resp = requests.get(art_url, headers={"User-Agent": cls.USER_AGENT}, timeout=10)
                    if art_resp.status_code == 200 and len(art_resp.content) > 1000:
                        artwork_bytes = art_resp.content
                except Exception as e:
                    logger.debug(f"Failed to fetch Deezer artwork: {e}")

            artist_obj = best_match.get("artist", {})
            artist_pic_url = None
            if isinstance(artist_obj, dict):
                artist_pic_url = (
                    artist_obj.get("picture_xl")
                    or artist_obj.get("picture_big")
                    or artist_obj.get("picture_medium")
                )

            artist_image_bytes = None
            if artist_pic_url:
                try:
                    pic_resp = requests.get(artist_pic_url, headers={"User-Agent": cls.USER_AGENT}, timeout=8)
                    if pic_resp.status_code == 200 and len(pic_resp.content) > 1000:
                        artist_image_bytes = pic_resp.content
                except Exception as e:
                    logger.debug(f"Failed to fetch Deezer artist picture: {e}")

            matched_artist = artist_obj.get("name", clean_meta.artist) if isinstance(artist_obj, dict) else clean_meta.artist
            primary_artist, extra_artists = TitleCleaner.extract_primary_artist(matched_artist)
            track_title = best_match.get("title", clean_meta.cleaned_title)
            # Strip "- Single" or "(Single)" from track title if present
            track_title = re.sub(r"\s*[-–—]\s*Single$", "", track_title, flags=re.IGNORECASE).strip()
            track_title = re.sub(r"[\(\[\{]\s*Single\s*[\)\]\}]", "", track_title, flags=re.IGNORECASE).strip()
            if extra_artists and not re.search(r"[\(\[\{]\s*(?:feat|ft)\.?\s+", track_title, re.IGNORECASE):
                track_title = f"{track_title} (feat. {extra_artists})"

            # If Deezer album is marked as a single, normalize to "Singles"
            if re.search(r"(?:[-–—\(\[]\s*single\s*[\)\]]?|^single$)", album_title, re.IGNORECASE):
                album_name = "Singles"
            else:
                album_name = album_title

            return EnrichedMetadata(
                title=track_title,
                artist=primary_artist,
                album=album_name,
                album_artist=primary_artist,
                artwork_bytes=artwork_bytes,
                artwork_mime="image/jpeg",
                source="deezer",
                artist_image_bytes=artist_image_bytes
            )

        except Exception as e:
            logger.debug(f"Deezer search failed: {e}")
            return None

    @classmethod
    def process_youtube_thumbnail(cls, thumbnail_bytes: bytes) -> bytes:
        """
        Process YouTube thumbnail: trim black bars and center-crop to 1:1 square.
        """
        try:
            img = Image.open(io.BytesIO(thumbnail_bytes))
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Check for letterboxing / black bars
            bbox = img.getbbox()
            if bbox:
                # If non-black area is a noticeable subregion, crop to it
                w_box = bbox[2] - bbox[0]
                h_box = bbox[3] - bbox[1]
                if w_box > 200 and h_box > 200:
                    img = img.crop(bbox)

            w, h = img.size
            min_dim = min(w, h)
            left = (w - min_dim) // 2
            top = (h - min_dim) // 2
            cropped = img.crop((left, top, left + min_dim, top + min_dim))

            output = io.BytesIO()
            cropped.save(output, format="JPEG", quality=95)
            return output.getvalue()
        except Exception as e:
            logger.warning(f"Error processing thumbnail image: {e}")
            return thumbnail_bytes

    @classmethod
    def enrich(
        cls,
        clean_meta: CleanMetadata,
        duration: Optional[int] = None,
        raw_thumbnail_bytes: Optional[bytes] = None,
        max_art_res: int = 3000,
        default_album_artist: str = "Various Artists"
    ) -> EnrichedMetadata:
        """
        Main enrichment entry point.
        Tries iTunes -> Deezer -> YouTube Fallback.
        """
        # 1. Try iTunes
        result = cls.query_itunes(clean_meta, duration=duration, max_art_res=max_art_res)

        # 2. Try Deezer
        deezer_result = cls.query_deezer(clean_meta, duration=duration)

        if result and result.artwork_bytes:
            if deezer_result and deezer_result.artist_image_bytes:
                result.artist_image_bytes = deezer_result.artist_image_bytes
            return result

        if deezer_result and deezer_result.artwork_bytes:
            if result:
                # Merge: iTunes metadata + Deezer artwork
                result.artwork_bytes = deezer_result.artwork_bytes
                result.artist_image_bytes = deezer_result.artist_image_bytes
                return result
            return deezer_result

        # If iTunes returned metadata without artwork, keep metadata but fallback artwork
        if result:
            if deezer_result and deezer_result.artist_image_bytes:
                result.artist_image_bytes = deezer_result.artist_image_bytes
            if raw_thumbnail_bytes:
                result.artwork_bytes = cls.process_youtube_thumbnail(raw_thumbnail_bytes)
            return result

        # If Deezer returned metadata without artwork, keep Deezer metadata but fallback artwork
        if deezer_result:
            if raw_thumbnail_bytes:
                deezer_result.artwork_bytes = cls.process_youtube_thumbnail(raw_thumbnail_bytes)
            return deezer_result

        # 3. Fallback to cleaned YouTube metadata + cropped thumbnail
        fallback_art = None
        if raw_thumbnail_bytes:
            fallback_art = cls.process_youtube_thumbnail(raw_thumbnail_bytes)

        return EnrichedMetadata(
            title=clean_meta.cleaned_title,
            artist=clean_meta.artist,
            album="Singles",
            album_artist=default_album_artist if clean_meta.artist == "Unknown Artist" else clean_meta.artist,
            artwork_bytes=fallback_art,
            artwork_mime="image/jpeg",
            source="youtube"
        )
