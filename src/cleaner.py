"""Title and artist cleaning and sanitization for chaotic YouTube video titles."""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class CleanMetadata:
    raw_title: str
    cleaned_title: str
    artist: str
    album_artist: Optional[str] = None
    featured_artists: Optional[str] = None


class TitleCleaner:
    # Junk words that indicate video metadata rather than musical content
    # Note: Deliberately excludes "remix", "live", "acoustic", "radio edit", "mix", "version", "instrumental"
    JUNK_KEYWORDS = (
        r"(?:"
        r"official\s+(?:music\s+|hd\s+|4k\s+)?video|"
        r"official\s+(?:hd\s+|4k\s+)?audio|"
        r"official\s+visualizer|"
        r"official\s+lyric\s+video|"
        r"official|"
        r"music\s+video|"
        r"clip\s+officiel|"
        r"video\s+oficiel|"
        r"video\s+oficial|"
        r"audio\s+oficial|"
        r"video\s+clip|"
        r"audio\s+only|"
        r"visualizer(?:\s+video)?|"
        r"color\s+coded\s+lyrics|"
        r"lyric(?:s)?(?:\s+video)?|"
        r"with\s+lyrics|"
        r"letra(?:s)?(?:\s+video)?|"
        r"paroles|"
        r"performance\s+video|"
        r"full\s+(?:song|track|album|audio)|"
        r"4k(?:\s*60fps)?|1080p(?:60)?|720p|hd|hq|uhd|"
        r"remaster(?:ed)?(?:\s+\d{4})?|"
        r"sub\s+español|eng\s+sub|"
        r"prod\.?\s+(?:by\s+)?[^\)\]\}】]+|"
        r"mv"
        r")"
    )

    # Brackets containing any of the junk keywords
    BRACKET_JUNK_REGEX = re.compile(
        r"[\(\[\{【](?=[^\)\]\}】]*\b" + JUNK_KEYWORDS + r"\b)[^\)\]\}】]*[\)\]\}】]",
        re.IGNORECASE
    )

    # Trailing pipe or dash junk like: | Official Video or - Official Video
    TRAILING_JUNK_REGEX = re.compile(
        r"\s*[\|\/]\s*(?:official\s+)?(?:music\s+)?(?:video|audio|visualizer).*$",
        re.IGNORECASE
    )

    # Clean channel / uploader names
    CHANNEL_JUNK = [
        r"\s*-\s*Topic$",
        r"VEVO$",
        r"\s+Official(\s+Channel)?$",
        r"\s+Music$",
        r"\s+Records$",
        r"\s+Entertainment$",
    ]

    @classmethod
    def clean_channel_name(cls, channel: Optional[str]) -> str:
        """Strip YouTube channel suffixes like ' - Topic', 'VEVO', ' Official'."""
        if not channel:
            return ""
        name = channel.strip()
        for pattern in cls.CHANNEL_JUNK:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()
        return name

    @classmethod
    def strip_junk(cls, text: str) -> str:
        """Remove video artifacts and clutter from title string."""
        cleaned = text

        # 1. Strip leading track numbers like "01. ", "1. ", "12) "
        cleaned = re.sub(r"^\s*\d{1,2}[\.\)]\s+", "", cleaned)

        # 2. Strip trailing pipes/slashes e.g. " | Official Video"
        cleaned = cls.TRAILING_JUNK_REGEX.sub("", cleaned)

        # 3. Strip bracketed junk like (Official Video), [4K], [Lyric Video]
        cleaned = cls.BRACKET_JUNK_REGEX.sub("", cleaned)

        # 4. Clean empty brackets left over: (), [], {}, 【】
        cleaned = re.sub(r"[\(\[\{【]\s*[\)\]\}】]", "", cleaned)

        # 5. Normalize double spaces and trim
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 6. Clean trailing / leading hyphens, pipes, dots
        cleaned = re.sub(r"^[\s\-\–\—\|\.\,\:\;]+|[\s\-\–\—\|\.\,\:\;]+$", "", cleaned).strip()
        return cleaned

    @classmethod
    def parse_artist_and_title(
        cls,
        video_title: str,
        channel_name: Optional[str] = None,
        yt_track: Optional[str] = None,
        yt_artist: Optional[str] = None
    ) -> CleanMetadata:
        """
        Extract clean Artist and Title from video metadata.
        Prioritizes yt-dlp native track/artist tags if available (common for YouTube Music),
        falling back to parsing video title and channel name.
        """
        # If yt-dlp already identified official music tags from YouTube Music:
        if yt_track and yt_artist:
            cleaned_track = cls.strip_junk(yt_track)
            cleaned_artist = cls.clean_channel_name(yt_artist)
            return CleanMetadata(
                raw_title=video_title,
                cleaned_title=cleaned_track,
                artist=cleaned_artist,
                album_artist=cleaned_artist
            )

        raw = video_title
        cleaned = cls.strip_junk(raw)
        channel = cls.clean_channel_name(channel_name)

        # Try to split by standard artist - title delimiters: " - ", " – ", " — ", " : "
        delimiters = [r"\s+[-–—]\s+", r"\s*:\s*", r"\s+\|\s+"]
        artist = ""
        title = cleaned

        split_found = False
        for delim in delimiters:
            parts = re.split(delim, cleaned, maxsplit=1)
            if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                part1 = parts[0].strip()
                part2 = parts[1].strip()

                # Check if channel matches part2 better, meaning it might be Title - Artist
                if channel and channel.lower() in part2.lower() and channel.lower() not in part1.lower():
                    artist = part2
                    title = part1
                else:
                    artist = part1
                    title = part2
                split_found = True
                break

        # Check for quotes: e.g. Artist "Title"
        if not split_found:
            quote_match = re.search(r'^(.*?)\s*["\'](.*?)["\']\s*$', cleaned)
            if quote_match and quote_match.group(1).strip() and quote_match.group(2).strip():
                artist = quote_match.group(1).strip()
                title = quote_match.group(2).strip()
                split_found = True

        # Fallback to channel name if no delimiter was found in the title
        if not split_found:
            if channel:
                artist = channel
                title = cleaned
            else:
                artist = "Unknown Artist"
                title = cleaned

        # Clean quotes and punctuation
        title = title.strip(' "\'').strip()
        artist = artist.strip(' "\'').strip()

        # Check for feat. / ft. in title and artist
        featured = None
        feat_match = re.search(r'[\(\[\{]?\s*(?:feat|ft)\.?\s+([^\)\]\}]+)[\)\]\}]?', title, flags=re.IGNORECASE)
        if feat_match:
            featured = feat_match.group(1).strip()

        # Standardize "feat." format if present in title
        title = re.sub(r'[\(\[\{]\s*(?:feat|ft)\.?\s+([^\)\]\}]+)[\)\]\}]', r'(feat. \1)', title, flags=re.IGNORECASE)
        # If feat was bare without brackets, wrap it nicely
        title = re.sub(r'(?<!\()\b(?:feat|ft)\.?\s+([^\(\[\{\-]+)$', r'(feat. \1)', title, flags=re.IGNORECASE)

        return CleanMetadata(
            raw_title=raw,
            cleaned_title=cls.strip_junk(title),
            artist=cls.clean_channel_name(artist) or "Unknown Artist",
            album_artist=cls.clean_channel_name(artist) or "Various Artists",
            featured_artists=featured
        )
