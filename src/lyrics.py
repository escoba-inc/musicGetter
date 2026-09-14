"""Lyrics retrieval via LRCLIB with fallback to YouTube subtitle (VTT) parsing."""

import logging
import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Optional, List
import requests

logger = logging.getLogger(__name__)

SPANISH_WORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "y",
    "que", "qué", "por", "para", "con", "sin", "mi", "tu", "su", "se", "me", "te",
    "nos", "lo", "al", "más", "mas", "pero", "como", "cómo", "cuando", "cuándo",
    "donde", "dónde", "quien", "quién", "siempre", "nunca", "todo", "nada", "amor",
    "noche", "vida", "días", "dias", "mundo", "corazón", "corazon", "yo", "ti", "ella",
    "él", "beso", "ojos", "quiero", "sé", "se", "ya", "solo", "sólo", "hasta", "tanto",
    "tiempo", "bonito", "fin", "otra", "otro", "nadie", "cancion", "canción"
}

ENGLISH_WORDS = {
    "the", "a", "an", "of", "in", "to", "for", "with", "on", "at", "from", "by", "about",
    "as", "into", "like", "through", "after", "over", "between", "out", "against", "during",
    "without", "before", "under", "around", "and", "but", "or", "nor", "so", "yet", "you",
    "me", "i", "my", "your", "we", "our", "they", "them", "love", "night", "heart", "dont",
    "cant", "wont", "its", "what", "when", "where", "who", "why", "how", "all", "no", "not",
    "girl", "boy", "time", "baby", "feat", "ft", "lights", "blinding", "save", "tears",
    "world", "eyes", "life", "day", "days", "away", "never", "always", "good", "bad", "give",
    "up", "down", "right", "left", "run", "running", "back", "home", "stay", "tell", "shape"
}

GERMAN_WORDS = {
    "der", "die", "das", "ein", "eine", "einer", "einem", "einen", "und", "in", "den",
    "von", "zu", "mit", "auf", "für", "fur", "ist", "im", "nicht", "dem", "sich", "ich",
    "du", "wir", "ihr", "sie", "liebe", "nacht", "hast", "alles", "immer", "wenn", "aus"
}

FRENCH_WORDS = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "en", "que", "qui", "pour",
    "dans", "sur", "avec", "sans", "mon", "ton", "son", "ce", "cette", "je", "tu", "il",
    "elle", "nous", "vous", "ils", "pas", "amour", "vie", "temps", "même", "meme"
}

PORTUGUESE_WORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "em", "no", "na",
    "nos", "nas", "e", "que", "para", "pra", "com", "sem", "meu", "seu", "sua", "você",
    "voce", "não", "nao", "amor", "vida", "coração", "coracao"
}

ITALIAN_WORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "del", "della", "dei",
    "a", "al", "alla", "da", "dal", "in", "con", "su", "per", "tra", "fra", "e", "che",
    "chi", "non", "io", "tu", "mio", "tuo", "suo", "amore", "notte", "vita"
}


def detect_language(title: str, artist: Optional[str] = None) -> str:
    """
    Detect the language of a track from its title and artist.
    Returns ISO 639-1 code ('es', 'en', 'de', 'fr', 'pt', 'it') or 'unknown'.
    """
    text = f"{title or ''} {artist or ''}".lower()
    scores = {"es": 0, "en": 0, "de": 0, "fr": 0, "pt": 0, "it": 0}

    # Distinctive character markers
    if re.search(r"[ñáéíóúü¿¡]", text):
        scores["es"] += 4
    if re.search(r"[äöüß]", text):
        scores["de"] += 4
    if re.search(r"[çœæêëèàâôûîï]", text):
        scores["fr"] += 4
    if re.search(r"[ãõ]", text):
        scores["pt"] += 4
    if re.search(r"[àèéìòù]", text):
        scores["it"] += 2

    # Morphological patterns for Spanish and English
    for token in re.findall(r"\b[a-z]{4,}\b", text):
        if token.endswith(("ito", "ita", "itos", "itas", "ando", "iendo", "mente")):
            scores["es"] += 3
        if token.endswith(("ing", "ight", "ness", "tion", "ment", "ever", "able")):
            scores["en"] += 3

    # Match tokens against vocabulary
    tokens = re.findall(r"\b\w+\b", text)
    for token in tokens:
        if token in SPANISH_WORDS:
            scores["es"] += 3
        if token in ENGLISH_WORDS:
            scores["en"] += 3
        if token in GERMAN_WORDS:
            scores["de"] += 3
        if token in FRENCH_WORDS:
            scores["fr"] += 3
        if token in PORTUGUESE_WORDS:
            scores["pt"] += 3
        if token in ITALIAN_WORDS:
            scores["it"] += 3

    best_lang = max(scores, key=scores.get)
    if scores[best_lang] > 0:
        return best_lang

    return "unknown"


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
        # 1. Exact match attempt
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
                item_dur = data.get("duration")
                if duration and item_dur and abs(item_dur - duration) > 6.0:
                    synced = None
                if synced or plain:
                    return LyricsResult(
                        synced_lyrics=synced,
                        plain_lyrics=plain,
                        source="lrclib"
                    )

            # 2. Search endpoint with multiple query variations
            search_url = "https://lrclib.net/api/search"
            # Try full title, and if it has (feat. ...) or brackets, also try stripped title
            clean_title = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title).strip()
            queries = [f"{artist} {title}"]
            if clean_title and clean_title.lower() != title.lower():
                queries.append(f"{artist} {clean_title}")

            for q in queries:
                search_resp = requests.get(
                    search_url,
                    params={"q": q},
                    headers={"User-Agent": cls.USER_AGENT},
                    timeout=8
                )
                if search_resp.status_code == 200:
                    results = search_resp.json()
                    if results and isinstance(results, list):
                        best_synced = None
                        best_plain = None
                        min_dur_diff = float("inf")

                        for item in results:
                            s_lyrics = item.get("syncedLyrics")
                            p_lyrics = item.get("plainLyrics")
                            item_dur = item.get("duration")

                            dur_diff = abs(item_dur - duration) if (duration and item_dur) else 0.0

                            # Prioritize candidates with syncedLyrics within 6s of audio duration
                            if s_lyrics and (not duration or dur_diff <= 6.0):
                                if dur_diff < min_dur_diff:
                                    min_dur_diff = dur_diff
                                    best_synced = s_lyrics
                                    best_plain = p_lyrics or best_plain

                            if p_lyrics and not best_plain:
                                best_plain = p_lyrics

                        if best_synced:
                            return LyricsResult(
                                synced_lyrics=best_synced,
                                plain_lyrics=best_plain,
                                source="lrclib"
                            )
                        elif best_plain:
                            return LyricsResult(
                                synced_lyrics=None,
                                plain_lyrics=best_plain,
                                source="lrclib"
                            )

        except Exception as e:
            logger.debug(f"LRCLIB request failed for {artist} - {title}: {e}")

        return None

    @classmethod
    def fetch_from_lyricsovh(cls, title: str, artist: str) -> Optional[LyricsResult]:
        """Fallback query to free open lyrics.ovh API for plain lyrics."""
        clean_title = re.sub(r"[\(\[\{].*?[\)\]\}]", "", title).strip()
        clean_artist = re.sub(r"[\(\[\{].*?[\)\]\}]", "", artist).strip()
        url = f"https://api.lyrics.ovh/v1/{urllib.parse.quote(clean_artist)}/{urllib.parse.quote(clean_title)}"
        try:
            resp = requests.get(url, headers={"User-Agent": cls.USER_AGENT}, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                lyrics_text = data.get("lyrics", "").strip()
                if lyrics_text:
                    return LyricsResult(
                        synced_lyrics=None,
                        plain_lyrics=lyrics_text,
                        source="lyrics_ovh"
                    )
        except Exception as e:
            logger.debug(f"lyrics.ovh failed for {artist} - {title}: {e}")
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
    def clean_subtitle_text(cls, text: str) -> str:
        """
        Thoroughly clean subtitle text:
        - Strip HTML/VTT tags like <c>, <c.color...>, </c>, <00:00:01.000>
        - Strip sound/acoustic tags between brackets or parentheses:
          Spanish: [música], [musica], [risas], [aplausos], [gritos], [suspiros], [silbidos], [sonido], [guitarra], etc.
          English: [music], [applause], [cheers], [laughter], [singing], [guitar solo], [beat], [gasp], [sigh], etc.
          French/German: [musique], [musik], [applaus], etc.
        - Strip musical notes (♪, ♫, ♩, ♬)
        - Strip generic audio tags enclosed in [] or () that don't contain lyrics
        - Normalize whitespace and clean dangling brackets/punctuation.
        """
        # Strip HTML/VTT tags
        clean = re.sub(r"<[^>]+>", "", text)

        # Strip musical notes: ♪, ♫, ♩, ♬
        clean = re.sub(r"[♪♫♩♬]+", "", clean)

        # Multilingual acoustic markers regex
        sound_markers = (
            r"m[uú]sica?|applause?|aplausos?|cheers?|laughter|laughing|risas?|singing|canto|"
            r"guitar(?:ra|\s+solo)?|drums?(?:\s+solo|\s+beat)?|bater[ií]a|beat|gritos?|screams?|"
            r"screaming|cheering|suspiros?|sighs?|jadeos?|gasps?|silbidos?|whistle?|whistling|"
            r"sonidos?|sounds?|audio|ruidos?|noise|crowd|ovaci[oó]n|estribillo|verso|"
            r"instrumental|silence|silencio|efecto|fx"
        )
        # Strip markers in brackets, parentheses, curly braces
        clean = re.sub(rf"[\(\[\{{]\s*(?:{sound_markers})\s*[\)\]\}}]", "", clean, flags=re.IGNORECASE)

        # Strip any remaining bracketed or parenthesized generic sound descriptions
        clean = re.sub(r"[\(\[\{][^\(\)\[\]\{\}]*?(?:m[uú]sic|sound|audio|riff|solo|beat)[^\(\)\[\]\{\}]*?[\)\]\}]", "", clean, flags=re.IGNORECASE)

        # Strip dangling brackets
        clean = re.sub(r"^[\[\(\{]\s*[\]\)\}]$", "", clean).strip()

        # Collapse whitespace
        clean = re.sub(r"\s+", " ", clean).strip()

        # If no word characters remain, treat as empty
        if not re.search(r"\w", clean):
            return ""

        return clean

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
                clean_text = cls.clean_subtitle_text(raw_text)
                if not clean_text:
                    continue

                # Deduplicate rolling captions
                if last_clean_text and clean_text.lower() == last_clean_text.lower():
                    continue
                if last_clean_text and clean_text.lower().startswith(last_clean_text.lower()):
                    if lrc_lines:
                        lrc_lines[-1] = f"{lrc_lines[-1].split(' ', 1)[0]} {clean_text}"
                        plain_lines[-1] = clean_text
                        last_clean_text = clean_text
                        continue
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
        Orchestrate lyrics retrieval with intelligent hierarchy prioritizing YouTube subtitles:
        1. Tier 1: YouTube Subtitles (timestamped lyrics matching the exact downloaded video audio).
                   Most faithful to video intros, dialogues, live edits, and tempo variations.
        2. Tier 2: LRCLIB Synced Lyrics (duration verified within 6s).
        3. Tier 3: LRCLIB Plain Text.
        4. Tier 4: lyrics.ovh Plain Text.
        """
        # Tier 1: YouTube Subtitles (exact audio match for downloaded video)
        if use_yt_subs and vtt_subtitle_path and os.path.exists(vtt_subtitle_path):
            try:
                with open(vtt_subtitle_path, "r", encoding="utf-8", errors="ignore") as f:
                    vtt_content = f.read()
                sub_res = cls.parse_vtt_to_lrc(vtt_content)
                if sub_res and sub_res.synced_lyrics:
                    return sub_res
            except Exception as e:
                logger.warning(f"Error parsing subtitle file {vtt_subtitle_path}: {e}")

        # Tier 2: LRCLIB Synced Lyrics (verified studio track)
        lrclib_res = None
        if use_lrclib:
            lrclib_res = cls.fetch_from_lrclib(title, artist, album, duration)
            if lrclib_res and lrclib_res.synced_lyrics:
                return lrclib_res

        # Tier 3: LRCLIB Plain Text
        if lrclib_res and lrclib_res.plain_lyrics:
            return lrclib_res

        # Tier 4: lyrics.ovh Plain Text
        ovh_res = cls.fetch_from_lyricsovh(title, artist)
        if ovh_res and ovh_res.plain_lyrics:
            return ovh_res

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
