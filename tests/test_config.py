"""Unit tests for config module."""

import unittest
import tempfile
import os
from unittest.mock import patch
from src.config import load_config, _parse_playlists_from_string


class TestConfig(unittest.TestCase):
    def test_load_config_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = load_config()
            self.assertEqual(cfg.audio.format, "opus")
            self.assertEqual(cfg.organization.structure, "standard")
            self.assertTrue(cfg.lyrics.enabled)
            self.assertTrue(cfg.artwork.embed)
            self.assertEqual(cfg.schedule.daily_at, "03:00")

    def test_parse_playlists_from_string(self):
        raw = """
        https://music.youtube.com/playlist?list=PL1 | Chill Beats
        https://www.youtube.com/playlist?list=PL2, https://youtube.com/playlist?list=PL3 | Rock
        # Comment line
        """
        playlists = _parse_playlists_from_string(raw)
        self.assertEqual(len(playlists), 3)
        self.assertEqual(playlists[0].url, "https://music.youtube.com/playlist?list=PL1")
        self.assertEqual(playlists[0].name, "Chill Beats")
        self.assertEqual(playlists[1].url, "https://www.youtube.com/playlist?list=PL2")
        self.assertIsNone(playlists[1].name)
        self.assertEqual(playlists[2].url, "https://youtube.com/playlist?list=PL3")
        self.assertEqual(playlists[2].name, "Rock")

    def test_load_config_from_env_vars(self):
        env = {
            "PLAYLISTS": "https://music.youtube.com/playlist?list=PL100 | Synthwave, https://youtube.com/playlist?list=PL200",
            "AUDIO_FORMAT": "m4a",
            "DAILY_AT": "05:15",
            "SYNC_ON_STARTUP": "false",
            "LYRICS_ENABLED": "true",
            "SAVE_LRC": "true",
            "COVER_RESOLUTION": "1400",
            "LIBRARY_DIR": "/custom/music",
            "DATA_DIR": "/custom/data",
            "COMPILATION_ALBUM_ARTIST": "Various",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertEqual(len(cfg.playlists), 2)
            self.assertEqual(cfg.playlists[0].name, "Synthwave")
            self.assertEqual(cfg.playlists[1].url, "https://youtube.com/playlist?list=PL200")
            self.assertEqual(cfg.audio.format, "m4a")
            self.assertEqual(cfg.schedule.daily_at, "05:15")
            self.assertFalse(cfg.schedule.sync_on_startup)
            self.assertEqual(cfg.artwork.max_resolution, 1400)
            self.assertEqual(cfg.library_dir, "/custom/music")
            self.assertEqual(cfg.data_dir, "/custom/data")
            self.assertEqual(cfg.organization.compilation_album_artist, "Various")

    def test_load_config_numbered_playlists(self):
        env = {
            "PLAYLIST_1": "https://music.youtube.com/playlist?list=PL_1 | List 1",
            "PLAYLIST_2": "https://music.youtube.com/playlist?list=PL_2 | List 2",
            "PLAYLIST_10": "https://music.youtube.com/playlist?list=PL_10 | List 10",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertEqual(len(cfg.playlists), 3)
            # Natural numeric sort: 1, then 2, then 10 (not 1, 10, 2)
            self.assertEqual(cfg.playlists[0].name, "List 1")
            self.assertEqual(cfg.playlists[1].name, "List 2")
            self.assertEqual(cfg.playlists[2].name, "List 10")

    def test_playlist_deduplication(self):
        env = {
            "PLAYLIST_1": "https://music.youtube.com/playlist?list=PL_SAME | First Name",
            "PLAYLIST_2": "https://music.youtube.com/playlist?list=PL_SAME | Duplicate",
            "PLAYLIST_3": "https://music.youtube.com/playlist?list=PL_DIFF",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = load_config()
            self.assertEqual(len(cfg.playlists), 2)
            self.assertEqual(cfg.playlists[0].url, "https://music.youtube.com/playlist?list=PL_SAME")
            self.assertEqual(cfg.playlists[0].name, "First Name")
            self.assertEqual(cfg.playlists[1].url, "https://music.youtube.com/playlist?list=PL_DIFF")

    def test_load_config_from_yaml(self):
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("""
playlists:
  - url: "https://music.youtube.com/playlist?list=PL123"
    name: "Synthwave"
  - "https://www.youtube.com/playlist?list=PL456"

library_dir: "/mnt/music"
data_dir: "/mnt/data"

audio:
  format: "m4a"
  quality: "best"
  replaygain: false

schedule:
  daily_at: "04:30"
  sync_on_startup: false
""")
            temp_path = f.name

        try:
            with patch.dict(os.environ, {}, clear=True):
                cfg = load_config(temp_path)
                self.assertEqual(len(cfg.playlists), 2)
                self.assertEqual(cfg.playlists[0].name, "Synthwave")
                self.assertEqual(cfg.playlists[1].url, "https://www.youtube.com/playlist?list=PL456")
                self.assertEqual(cfg.library_dir, "/mnt/music")
                self.assertEqual(cfg.data_dir, "/mnt/data")
                self.assertEqual(cfg.audio.format, "m4a")
                self.assertFalse(cfg.audio.replaygain)
                self.assertEqual(cfg.schedule.daily_at, "04:30")
                self.assertFalse(cfg.schedule.sync_on_startup)
        finally:
            os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
