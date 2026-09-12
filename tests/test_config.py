"""Unit tests for config module."""

import unittest
import tempfile
import os
from src.config import load_config


class TestConfig(unittest.TestCase):
    def test_load_config_defaults(self):
        cfg = load_config()
        self.assertEqual(cfg.audio.format, "opus")
        self.assertEqual(cfg.organization.structure, "standard")
        self.assertTrue(cfg.lyrics.enabled)
        self.assertTrue(cfg.artwork.embed)
        self.assertEqual(cfg.schedule.daily_at, "03:00")

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

lyrics:
  enabled: true
  save_lrc: true
  use_youtube_subtitles: true

schedule:
  daily_at: "04:30"
  sync_on_startup: false
""")
            temp_path = f.name

        try:
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
