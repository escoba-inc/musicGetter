"""Main orchestration engine and daemon scheduler for MusicGetter."""

import argparse
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
import time
from typing import Optional, List

import schedule

from src.cleaner import TitleCleaner
from src.config import AppConfig, load_config
from src.database import Database
from src.downloader import Downloader
from src.lyrics import LyricsManager
from src.metadata import MetadataEnricher
from src.playlist import PlaylistGenerator, sanitize_filename
from src.tagger import AudioTagger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("musicGetter")


class MusicGetter:
    def __init__(self, config: AppConfig):
        self.config = config
        db_path = os.path.join(config.data_dir, "library.db")
        self.db = Database(db_path)
        self.downloader = Downloader(cookies_file=config.cookies_file)

    def _determine_destination_path(
        self,
        artist: str,
        album: str,
        title: str,
        track_number: Optional[int],
        audio_ext: str
    ) -> str:
        """Construct the target file path inside library_dir."""
        safe_artist = sanitize_filename(artist, fallback="Unknown Artist")
        safe_album = sanitize_filename(album or "Singles", fallback="Singles")
        safe_title = sanitize_filename(title, fallback="Unknown Title")

        if self.config.organization.structure == "flat":
            filename = f"{safe_artist} - {safe_title}{audio_ext}"
            return os.path.join(self.config.library_dir, filename)

        # Default "standard" hierarchy: /music/Artist/Album/01 - Title.opus
        album_dir = os.path.join(self.config.library_dir, safe_artist, safe_album)
        os.makedirs(album_dir, exist_ok=True)

        if track_number is not None and track_number > 0:
            filename = f"{track_number:02d} - {safe_title}{audio_ext}"
        else:
            filename = f"{safe_title}{audio_ext}"

        return os.path.join(album_dir, filename)

    def sync_playlist(self, playlist_url: str, custom_name: Optional[str] = None) -> Optional[str]:
        """Synchronize a single YouTube/YouTube Music playlist. Returns playlist_id."""
        logger.info(f"Checking playlist: {playlist_url}")
        info = self.downloader.get_playlist_info(playlist_url)
        if not info:
            logger.warning(f"Could not retrieve playlist info from {playlist_url}")
            return None

        playlist_name = custom_name or info.title
        logger.info(f"Syncing playlist '{playlist_name}' ({len(info.entries)} tracks found)")

        synced_youtube_ids = []

        with tempfile.TemporaryDirectory() as temp_work_dir:
            for index, entry in enumerate(info.entries, start=1):
                yt_id = entry["id"]
                video_title = entry["title"]
                uploader = entry.get("channel", "")

                synced_youtube_ids.append(yt_id)

                # Deduplication check
                if self.db.is_downloaded(yt_id):
                    logger.debug(f"[{index}/{len(info.entries)}] Already in library: {video_title} ({yt_id})")
                    continue

                logger.info(f"[{index}/{len(info.entries)}] Downloading: {video_title} ({yt_id})")

                try:
                    # Step 1: Download track audio, thumbnail, subtitles
                    downloaded = self.downloader.download_track(
                        youtube_id=yt_id,
                        temp_dir=temp_work_dir,
                        audio_format=self.config.audio.format,
                        download_subs=self.config.lyrics.use_youtube_subtitles,
                        subtitle_languages=self.config.lyrics.subtitle_languages
                    )

                    if not downloaded or not os.path.exists(downloaded.audio_path):
                        logger.error(f"Failed to download audio for {video_title} ({yt_id})")
                        continue

                    # Step 2: Clean title and artist
                    clean_meta = TitleCleaner.parse_artist_and_title(
                        video_title=downloaded.raw_title or video_title,
                        channel_name=downloaded.channel or uploader,
                        yt_track=downloaded.yt_track,
                        yt_artist=downloaded.yt_artist
                    )

                    # Step 3: Read raw thumbnail if available
                    raw_thumb_bytes = None
                    if downloaded.thumbnail_path and os.path.exists(downloaded.thumbnail_path):
                        try:
                            with open(downloaded.thumbnail_path, "rb") as tf:
                                raw_thumb_bytes = tf.read()
                        except Exception as e:
                            logger.debug(f"Could not read thumbnail file: {e}")

                    # Step 4: Metadata and High-Res Cover Art Enrichment (iTunes / Deezer / Fallback)
                    enriched = MetadataEnricher.enrich(
                        clean_meta=clean_meta,
                        duration=downloaded.duration,
                        raw_thumbnail_bytes=raw_thumb_bytes,
                        max_art_res=self.config.artwork.max_resolution,
                        default_album_artist=self.config.organization.compilation_album_artist
                    )

                    # Step 5: Lyrics (LRCLIB -> YouTube Subtitles fallback)
                    lyrics_res = None
                    has_lyrics = False
                    if self.config.lyrics.enabled:
                        lyrics_res = LyricsManager.get_lyrics(
                            title=enriched.title,
                            artist=enriched.artist,
                            album=enriched.album,
                            duration=downloaded.duration,
                            vtt_subtitle_path=downloaded.subtitle_path,
                            use_lrclib=self.config.lyrics.use_lrclib,
                            use_yt_subs=self.config.lyrics.use_youtube_subtitles
                        )
                        has_lyrics = bool(lyrics_res.synced_lyrics or lyrics_res.plain_lyrics)

                    # Step 6: Move audio file to final destination
                    _, ext = os.path.splitext(downloaded.audio_path)
                    final_path = self._determine_destination_path(
                        artist=enriched.artist,
                        album=enriched.album,
                        title=enriched.title,
                        track_number=enriched.track_number,
                        audio_ext=ext
                    )

                    dest_dir = os.path.dirname(final_path)
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(downloaded.audio_path, final_path)

                    # Step 7: Save sidecar cover.jpg if requested and artwork exists
                    if self.config.artwork.save_cover_jpg and enriched.artwork_bytes:
                        cover_jpg_path = os.path.join(dest_dir, "cover.jpg")
                        if not os.path.exists(cover_jpg_path):
                            try:
                                with open(cover_jpg_path, "wb") as cf:
                                    cf.write(enriched.artwork_bytes)
                            except Exception as e:
                                logger.warning(f"Could not save cover.jpg: {e}")

                    # Step 7b: Save artist.jpg in artist folder if not already present
                    safe_artist = sanitize_filename(enriched.artist, fallback="Unknown Artist")
                    if safe_artist != "Various Artists":
                        artist_dir = os.path.dirname(dest_dir) if self.config.organization.structure == "standard" else dest_dir
                        artist_jpg_path = os.path.join(artist_dir, "artist.jpg")
                        if not os.path.exists(artist_jpg_path):
                            artist_art = enriched.artist_image_bytes
                            if not artist_art and downloaded.channel_url:
                                logger.info(f"Artist photo not found on Deezer/iTunes for {enriched.artist}, fetching YouTube channel avatar from {downloaded.channel_url}")
                                artist_art = Downloader.download_channel_avatar(downloaded.channel_url)
                            if artist_art:
                                try:
                                    with open(artist_jpg_path, "wb") as af:
                                        af.write(artist_art)
                                    logger.info(f"Saved artist image: {artist_jpg_path}")
                                except Exception as e:
                                    logger.warning(f"Could not save artist.jpg: {e}")

                    # Step 8: Save sidecar .lrc file if lyrics available (synced or plain)
                    lyrics_to_save = lyrics_res.synced_lyrics or lyrics_res.plain_lyrics if lyrics_res else None
                    if self.config.lyrics.save_lrc and lyrics_to_save:
                        LyricsManager.save_lrc_file(final_path, lyrics_to_save)

                    # Step 9: Tag audio file with Mutagen
                    lyrics_to_embed = lyrics_res.synced_lyrics or lyrics_res.plain_lyrics if lyrics_res else None
                    AudioTagger.apply_tags(
                        file_path=final_path,
                        title=enriched.title,
                        artist=enriched.artist,
                        album=enriched.album,
                        album_artist=enriched.album_artist,
                        track_number=enriched.track_number,
                        year=enriched.year,
                        genre=enriched.genre,
                        lyrics=lyrics_to_embed if self.config.lyrics.embed else None,
                        artwork_bytes=enriched.artwork_bytes if self.config.artwork.embed else None,
                        artwork_mime=enriched.artwork_mime
                    )

                    # Step 10: Record in database
                    self.db.save_track(
                        youtube_id=yt_id,
                        file_path=final_path,
                        title=enriched.title,
                        artist=enriched.artist,
                        album=enriched.album,
                        duration=downloaded.duration,
                        format_name=self.config.audio.format,
                        has_lyrics=has_lyrics
                    )

                    logger.info(f"Saved & Tagged: {enriched.artist} - {enriched.title} ({enriched.source})")
                finally:
                    # Clean up per-track temporary artifacts immediately to preserve disk space
                    track_temp_dir = os.path.join(temp_work_dir, yt_id)
                    if os.path.exists(track_temp_dir):
                        shutil.rmtree(track_temp_dir, ignore_errors=True)

        # Step 11: Update playlist record and generate Navidrome .m3u8 playlist
        self.db.update_playlist(
            playlist_id=info.playlist_id,
            name=playlist_name,
            url=playlist_url,
            youtube_ids=synced_youtube_ids
        )

        if self.config.organization.generate_m3u8:
            playlist_tracks = self.db.get_playlist_tracks(info.playlist_id)
            PlaylistGenerator.generate_m3u8(
                playlist_name=playlist_name,
                tracks=playlist_tracks,
                playlists_dir=self.config.organization.playlists_dir
            )

        return info.playlist_id

    def cleanup_orphans(self, active_playlist_ids: List[str]):
        """
        Delete tracks that are no longer in any active playlist,
        as well as playlists that have been removed from configuration.
        """
        if not self.config.organization.cleanup_removed_tracks:
            return

        # 1. Clean up stale playlists (removed from config)
        stale_playlists = self.db.get_stale_playlists(active_playlist_ids)
        for st_pl in stale_playlists:
            pl_id = st_pl["playlist_id"]
            pl_name = st_pl["name"]
            m3u8_path = os.path.join(
                self.config.organization.playlists_dir,
                f"{sanitize_filename(pl_name)}.m3u8"
            )
            if os.path.exists(m3u8_path):
                try:
                    os.remove(m3u8_path)
                    logger.info(f"Removed deleted playlist file: {m3u8_path}")
                except Exception as e:
                    logger.warning(f"Could not remove playlist file {m3u8_path}: {e}")
            self.db.delete_playlist(pl_id)

        # 2. Clean up orphan tracks (tracks that belong to 0 active playlists)
        orphan_tracks = self.db.get_orphan_tracks(active_playlist_ids)
        if orphan_tracks:
            logger.info(f"Cleaning up {len(orphan_tracks)} track(s) removed from all playlists...")

        for track in orphan_tracks:
            yt_id = track["youtube_id"]
            file_path = track["file_path"]
            title = track.get("title", yt_id)
            artist = track.get("artist", "")

            # Remove audio file
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"Deleted removed track: {artist} - {title} ({file_path})")
                except Exception as e:
                    logger.warning(f"Could not delete audio file {file_path}: {e}")

            # Remove sidecar .lrc file if exists
            base, _ = os.path.splitext(file_path)
            lrc_path = f"{base}.lrc"
            if os.path.exists(lrc_path):
                try:
                    os.remove(lrc_path)
                except Exception as e:
                    logger.debug(f"Could not delete sidecar .lrc: {e}")

            # Remove empty album/artist directories to prevent ghost folders in Navidrome
            track_dir = os.path.dirname(file_path)
            self._cleanup_empty_directories(track_dir)

            # Remove from database
            self.db.delete_track(yt_id)

    def _cleanup_empty_directories(self, directory: str):
        """Recursively delete empty folders up to library_dir."""
        try:
            lib_dir = os.path.abspath(self.config.library_dir)
            current = os.path.abspath(directory)
            while current != lib_dir and current.startswith(lib_dir):
                entries = os.listdir(current)
                # If directory is empty or only has an orphaned cover.jpg left
                if entries == ["cover.jpg"] or not entries:
                    if entries == ["cover.jpg"]:
                        os.remove(os.path.join(current, "cover.jpg"))
                    os.rmdir(current)
                    logger.debug(f"Removed empty directory: {current}")
                    current = os.path.dirname(current)
                else:
                    break
        except Exception as e:
            logger.debug(f"Directory cleanup notice: {e}")

    def migrate_multi_artist_tracks(self):
        """
        Scan existing library tracks and automatically migrate:
        1. Joined collaboration artists to their primary artist folder (e.g. 'Jim Yosef & Scarlett' -> 'Jim Yosef').
        2. Albums with '- Single' / '(Single)' to clean 'Singles' album folder.
        3. Titles containing '- Single' / '(Single)'.
        4. Populate missing .lrc synced lyrics.
        """
        all_tracks = self.db.get_all_tracks()
        migrated_count = 0

        for track in all_tracks:
            yt_id = track["youtube_id"]
            old_path = track["file_path"]
            if not os.path.exists(old_path):
                continue

            old_artist = track.get("artist", "")
            primary_artist, extra = TitleCleaner.extract_primary_artist(old_artist)

            old_title = track.get("title", "")
            new_title = old_title
            new_title = re.sub(r"\s*[-–—]\s*(?:single|ep)$", "", new_title, flags=re.IGNORECASE).strip()
            new_title = re.sub(r"[\(\[\{]\s*(?:single|ep)\s*[\)\]\}]", "", new_title, flags=re.IGNORECASE).strip()
            if extra and not re.search(r"[\(\[\{]\s*(?:feat|ft)\.?\s+", new_title, re.IGNORECASE):
                new_title = f"{new_title} (feat. {extra})"

            old_album = track.get("album", "Singles")
            if re.search(r"(?:[-–—\(\[]\s*single\s*[\)\]]?|^single$)", old_album, re.IGNORECASE):
                new_album = "Singles"
            else:
                new_album = old_album

            track_num = None
            old_base_name = os.path.basename(old_path)
            num_match = re.match(r"^(\d{1,2})\s*-\s*", old_base_name)
            if num_match:
                try:
                    track_num = int(num_match.group(1))
                except ValueError:
                    track_num = None

            _, ext = os.path.splitext(old_path)
            new_path = self._determine_destination_path(
                artist=primary_artist,
                album=new_album,
                title=new_title,
                track_number=track_num,
                audio_ext=ext
            )

            path_changed = (os.path.abspath(new_path) != os.path.abspath(old_path))
            tags_changed = (primary_artist != old_artist or new_album != old_album or new_title != old_title)

            current_path = old_path
            if path_changed:
                try:
                    dest_dir = os.path.dirname(new_path)
                    os.makedirs(dest_dir, exist_ok=True)

                    shutil.move(old_path, new_path)

                    old_base, _ = os.path.splitext(old_path)
                    new_base, _ = os.path.splitext(new_path)
                    if os.path.exists(f"{old_base}.lrc"):
                        shutil.move(f"{old_base}.lrc", f"{new_base}.lrc")

                    old_dir = os.path.dirname(old_path)
                    old_cover = os.path.join(old_dir, "cover.jpg")
                    new_cover = os.path.join(dest_dir, "cover.jpg")
                    if os.path.exists(old_cover) and not os.path.exists(new_cover):
                        shutil.copy2(old_cover, new_cover)

                    self._cleanup_empty_directories(old_dir)
                    current_path = new_path
                except Exception as e:
                    logger.warning(f"Failed to move file {old_path} to {new_path}: {e}")
                    continue

            if path_changed or tags_changed:
                try:
                    AudioTagger.apply_tags(
                        file_path=current_path,
                        title=new_title,
                        artist=primary_artist,
                        album=new_album,
                        album_artist=primary_artist
                    )
                    self.db.update_track_metadata(
                        youtube_id=yt_id,
                        file_path=current_path,
                        title=new_title,
                        artist=primary_artist,
                        album=new_album
                    )
                    migrated_count += 1
                except Exception as e:
                    logger.warning(f"Failed to update tags for {current_path}: {e}")

            # Check for missing sidecar .lrc
            base_cur, _ = os.path.splitext(current_path)
            lrc_file = f"{base_cur}.lrc"
            if self.config.lyrics.save_lrc and not os.path.exists(lrc_file):
                try:
                    l_res = LyricsManager.get_lyrics(
                        title=new_title,
                        artist=primary_artist,
                        album=new_album,
                        duration=track.get("duration"),
                        use_lrclib=self.config.lyrics.use_lrclib,
                        use_yt_subs=self.config.lyrics.use_youtube_subtitles
                    )
                    lyrics_to_save = l_res.synced_lyrics or l_res.plain_lyrics if l_res else None
                    if lyrics_to_save:
                        LyricsManager.save_lrc_file(current_path, lyrics_to_save)
                        self.db.update_track_metadata(
                            youtube_id=yt_id,
                            file_path=current_path,
                            title=new_title,
                            artist=primary_artist,
                            album=new_album,
                            has_lyrics=True
                        )
                except Exception as e:
                    logger.debug(f"Failed to refresh lyrics for {new_title}: {e}")

        if migrated_count > 0:
            logger.info(f"Successfully migrated {migrated_count} library track(s) (artists, singles & tags).")
            if self.config.organization.generate_m3u8:
                for pl in self.db.get_all_playlists():
                    tracks = self.db.get_playlist_tracks(pl["playlist_id"])
                    PlaylistGenerator.generate_m3u8(
                        playlist_name=pl["name"],
                        tracks=tracks,
                        playlists_dir=self.config.organization.playlists_dir
                    )

    def sync_all(self):
        """Run synchronization across all configured playlists and prune removed songs."""
        # 1. Migrate any existing multi-artist folders to primary artist folders
        self.migrate_multi_artist_tracks()

        if not self.config.playlists:
            logger.warning("No playlists configured in docker-compose.yml.")
            return

        logger.info(f"Starting sync cycle for {len(self.config.playlists)} playlist(s)...")
        active_playlist_ids = []
        has_sync_errors = False
        for pl in self.config.playlists:
            try:
                pl_id = self.sync_playlist(pl.url, custom_name=pl.name)
                if pl_id:
                    active_playlist_ids.append(pl_id)
                else:
                    has_sync_errors = True
            except Exception as e:
                logger.error(f"Error syncing playlist {pl.url}: {e}", exc_info=True)
                has_sync_errors = True

        # Automatic cleanup: Remove any song or playlist that is no longer in any list
        # CRITICAL SAFETY CHECK: Never delete songs if any playlist had errors during sync!
        if has_sync_errors:
            logger.warning("One or more playlists failed to sync. Skipping orphan cleanup to protect library from accidental deletion.")
        elif active_playlist_ids and self.config.organization.cleanup_removed_tracks:
            self.cleanup_orphans(active_playlist_ids)

        logger.info("Sync cycle completed.")


def run_daemon(config: AppConfig):
    """Run MusicGetter daemon according to the configured schedule with graceful shutdown."""
    getter = MusicGetter(config)

    running = True

    def handle_shutdown(signum, frame):
        nonlocal running
        logger.info("Shutdown signal received. Exiting daemon gracefully...")
        running = False

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    if config.schedule.sync_on_startup:
        logger.info("Performing initial sync on startup...")
        getter.sync_all()

    sync_time = config.schedule.daily_at
    logger.info(f"Scheduling daily sync at {sync_time}...")
    schedule.every().day.at(sync_time).do(getter.sync_all)

    while running:
        schedule.run_pending()
        time.sleep(1)

    logger.info("MusicGetter daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="MusicGetter: Sync YouTube Music playlists with Navidrome")
    parser.add_argument("--config", "-c", help="Path to config.yaml", default=None)
    parser.add_argument("--sync-now", action="store_true", help="Run synchronization once immediately and exit")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    if args.sync_now:
        getter = MusicGetter(config)
        getter.sync_all()
        sys.exit(0)
    else:
        run_daemon(config)


if __name__ == "__main__":
    main()
