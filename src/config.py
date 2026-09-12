"""Configuration loader and schema validation for MusicGetter."""

import os
import yaml
from dataclasses import dataclass, field
from typing import List, Optional


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


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """Load configuration from YAML file and apply environment variable overrides."""
    if not config_path:
        config_path = os.environ.get("MUSICGETTER_CONFIG")
        if not config_path:
            # Check default candidate locations
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

    raw_cfg = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f) or {}
    elif config_path:
        raise FileNotFoundError(f"Config file specified but not found: {config_path}")

    # Parse Playlists
    playlists: List[PlaylistConfig] = []
    for item in raw_cfg.get("playlists", []):
        if isinstance(item, str):
            playlists.append(PlaylistConfig(url=item.strip()))
        elif isinstance(item, dict) and "url" in item:
            playlists.append(PlaylistConfig(
                url=item["url"].strip(),
                name=item.get("name")
            ))

    # Env overrides for directories
    library_dir = os.environ.get("LIBRARY_DIR", raw_cfg.get("library_dir", "/music"))
    data_dir = os.environ.get("DATA_DIR", raw_cfg.get("data_dir", "/config"))

    # Audio
    audio_data = raw_cfg.get("audio", {})
    audio_cfg = AudioConfig(
        format=audio_data.get("format", "opus").lower(),
        quality=audio_data.get("quality", "best"),
        replaygain=audio_data.get("replaygain", True)
    )

    # Organization
    org_data = raw_cfg.get("organization", {})
    org_cfg = OrganizationConfig(
        structure=org_data.get("structure", "standard").lower(),
        compilation_album_artist=org_data.get("compilation_album_artist", "Various Artists"),
        generate_m3u8=org_data.get("generate_m3u8", True),
        playlists_dir=org_data.get("playlists_dir", os.path.join(library_dir, "playlists"))
    )

    # Lyrics
    lyr_data = raw_cfg.get("lyrics", {})
    lyrics_cfg = LyricsConfig(
        enabled=lyr_data.get("enabled", True),
        embed=lyr_data.get("embed", True),
        save_lrc=lyr_data.get("save_lrc", True),
        use_lrclib=lyr_data.get("use_lrclib", True),
        use_youtube_subtitles=lyr_data.get("use_youtube_subtitles", True),
        subtitle_languages=lyr_data.get("subtitle_languages", "en.*,es.*,all")
    )

    # Artwork
    art_data = raw_cfg.get("artwork", {})
    artwork_cfg = ArtworkConfig(
        embed=art_data.get("embed", True),
        save_cover_jpg=art_data.get("save_cover_jpg", True),
        max_resolution=int(art_data.get("max_resolution", 3000)),
        crop_youtube_thumbnail=art_data.get("crop_youtube_thumbnail", True)
    )

    # Schedule
    sched_data = raw_cfg.get("schedule", {})
    schedule_cfg = ScheduleConfig(
        daily_at=sched_data.get("daily_at", "03:00"),
        sync_on_startup=sched_data.get("sync_on_startup", True)
    )

    # Cookies
    cookies_file = raw_cfg.get("cookies_file")
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
