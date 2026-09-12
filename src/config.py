"""Configuration loader supporting environment variables (docker-compose) and YAML files."""

import os
import re
import yaml
from dataclasses import dataclass, field
from typing import List, Optional, Any


@dataclass
class PlaylistConfig:
    url: str
    name: Optional[str] = None


@dataclass
class AudioConfig:
    format: str = "opus"          # "opus", "m4a", "mp3"
    quality: str = "best"
    replaygain: bool = True


@dataclass
class OrganizationConfig:
    structure: str = "standard"   # "standard", "flat"
    compilation_album_artist: str = "Various Artists"
    generate_m3u8: bool = True
    playlists_dir: str = "/music/playlists"


@dataclass
class LyricsConfig:
    enabled: bool = True
    embed: bool = True
    save_lrc: bool = True
    use_lrclib: bool = True
    use_youtube_subtitles: bool = True
    subtitle_languages: str = "en.*,es.*,all"


@dataclass
class ArtworkConfig:
    embed: bool = True
    save_cover_jpg: bool = True
    max_resolution: int = 3000
    crop_youtube_thumbnail: bool = True


@dataclass
class ScheduleConfig:
    daily_at: str = "03:00"
    sync_on_startup: bool = True


@dataclass
class AppConfig:
    playlists: List[PlaylistConfig] = field(default_factory=list)
    library_dir: str = "/music"
    data_dir: str = "/config"
    audio: AudioConfig = field(default_factory=AudioConfig)
    organization: OrganizationConfig = field(default_factory=OrganizationConfig)
    lyrics: LyricsConfig = field(default_factory=LyricsConfig)
    artwork: ArtworkConfig = field(default_factory=ArtworkConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    cookies_file: Optional[str] = None


def _parse_bool(val: Any, default: bool = True) -> bool:
    """Parse boolean from string or boolean value."""
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes", "on", "t")


def _parse_playlists_from_string(val: str) -> List[PlaylistConfig]:
    """
    Parse playlist URLs from string supporting:
    - Multiline: URL | Custom Name
    - Comma-separated: URL1 | Name, URL2
    - Semicolon-separated
    """
    results = []
    lines = val.strip().splitlines()
    entries = []
    for line in lines:
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue
        # Split by comma or semicolon
        for item in re.split(r"[,;]", line_clean):
            item_clean = item.strip()
            if item_clean:
                entries.append(item_clean)

    for entry in entries:
        parts = [p.strip() for p in entry.split("|", 1)]
        url = parts[0]
        name = parts[1] if len(parts) > 1 and parts[1] else None
        if url:
            results.append(PlaylistConfig(url=url, name=name))
    return results


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """
    Load configuration prioritizing environment variables (perfect for docker-compose),
    with optional fallback to a YAML file.
    """
    raw_cfg = {}

    if not config_path:
        config_path = os.environ.get("MUSICGETTER_CONFIG")
        if not config_path:
            candidates = [
                "/config/config.yaml",
                "/config/config.yml",
                "config.yaml",
                "config.yml",
            ]
            for candidate in candidates:
                if os.path.exists(candidate):
                    config_path = candidate
                    break

    # If YAML config exists, read it
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}

    # --- 1. Playlists (Environment Variables take precedence) ---
    playlists: List[PlaylistConfig] = []

    # Check PLAYLISTS environment variable (multiline or comma-separated)
    env_playlists = os.environ.get("PLAYLISTS")
    if env_playlists and env_playlists.strip():
        playlists.extend(_parse_playlists_from_string(env_playlists))

    # Check numbered environment variables: PLAYLIST_1, PLAYLIST_2, etc.
    numbered_keys = sorted([k for k in os.environ if re.match(r"^PLAYLIST_\d+$", k, re.IGNORECASE)])
    for k in numbered_keys:
        val = os.environ[k].strip()
        if val:
            playlists.extend(_parse_playlists_from_string(val))

    # Fallback to YAML playlists if env vars were not provided
    if not playlists and "playlists" in raw_cfg:
        for item in raw_cfg.get("playlists", []):
            if isinstance(item, str):
                playlists.extend(_parse_playlists_from_string(item))
            elif isinstance(item, dict) and "url" in item:
                playlists.append(PlaylistConfig(
                    url=item["url"].strip(),
                    name=item.get("name")
                ))

    # --- 2. Directories ---
    library_dir = os.environ.get("LIBRARY_DIR", raw_cfg.get("library_dir", "/music"))
    data_dir = os.environ.get("DATA_DIR", raw_cfg.get("data_dir", "/config"))

    # --- 3. Audio Settings ---
    audio_data = raw_cfg.get("audio", {})
    audio_cfg = AudioConfig(
        format=os.environ.get("AUDIO_FORMAT", audio_data.get("format", "opus")).lower(),
        quality=os.environ.get("AUDIO_QUALITY", audio_data.get("quality", "best")),
        replaygain=_parse_bool(os.environ.get("AUDIO_REPLAYGAIN", audio_data.get("replaygain", True)))
    )

    # --- 4. Organization Settings ---
    org_data = raw_cfg.get("organization", {})
    playlists_dir_default = os.path.join(library_dir, "playlists")
    org_cfg = OrganizationConfig(
        structure=os.environ.get("STRUCTURE", org_data.get("structure", "standard")).lower(),
        compilation_album_artist=os.environ.get("COMPILATION_ALBUM_ARTIST", org_data.get("compilation_album_artist", "Various Artists")),
        generate_m3u8=_parse_bool(os.environ.get("GENERATE_M3U8", org_data.get("generate_m3u8", True))),
        playlists_dir=os.environ.get("PLAYLISTS_DIR", org_data.get("playlists_dir", playlists_dir_default))
    )

    # --- 5. Lyrics Settings ---
    lyr_data = raw_cfg.get("lyrics", {})
    lyrics_cfg = LyricsConfig(
        enabled=_parse_bool(os.environ.get("LYRICS_ENABLED", lyr_data.get("enabled", True))),
        embed=_parse_bool(os.environ.get("LYRICS_EMBED", lyr_data.get("embed", True))),
        save_lrc=_parse_bool(os.environ.get("SAVE_LRC", lyr_data.get("save_lrc", True))),
        use_lrclib=_parse_bool(os.environ.get("USE_LRCLIB", lyr_data.get("use_lrclib", True))),
        use_youtube_subtitles=_parse_bool(os.environ.get("USE_YOUTUBE_SUBTITLES", lyr_data.get("use_youtube_subtitles", True))),
        subtitle_languages=os.environ.get("SUBTITLE_LANGUAGES", lyr_data.get("subtitle_languages", "en.*,es.*,all"))
    )

    # --- 6. Artwork Settings ---
    art_data = raw_cfg.get("artwork", {})
    artwork_cfg = ArtworkConfig(
        embed=_parse_bool(os.environ.get("ARTWORK_EMBED", art_data.get("embed", True))),
        save_cover_jpg=_parse_bool(os.environ.get("SAVE_COVER_JPG", art_data.get("save_cover_jpg", True))),
        max_resolution=int(os.environ.get("COVER_RESOLUTION", art_data.get("max_resolution", 3000))),
        crop_youtube_thumbnail=_parse_bool(os.environ.get("CROP_YOUTUBE_THUMBNAIL", art_data.get("crop_youtube_thumbnail", True)))
    )

    # --- 7. Schedule Settings ---
    sched_data = raw_cfg.get("schedule", {})
    schedule_cfg = ScheduleConfig(
        daily_at=os.environ.get("DAILY_AT", sched_data.get("daily_at", "03:00")),
        sync_on_startup=_parse_bool(os.environ.get("SYNC_ON_STARTUP", sched_data.get("sync_on_startup", True)))
    )

    # --- 8. Cookies ---
    cookies_file = os.environ.get("COOKIES_FILE", raw_cfg.get("cookies_file"))
    if not cookies_file:
        candidate_cookie = os.path.join(data_dir, "cookies.txt")
        if os.path.exists(candidate_cookie):
            cookies_file = candidate_cookie

    return AppConfig(
        playlists=playlists,
        library_dir=library_dir,
        data_dir=data_dir,
        audio=audio_cfg,
        organization=org_cfg,
        lyrics=lyrics_cfg,
        artwork=artwork_cfg,
        schedule=schedule_cfg,
        cookies_file=cookies_file
    )
