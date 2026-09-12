"""Unit tests for PlaylistGenerator."""

import unittest
import tempfile
import os
from src.playlist import PlaylistGenerator, sanitize_filename


class TestPlaylistGenerator(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Rock & Roll: Best Hits?"), "Rock & Roll- Best Hits-")
        self.assertEqual(sanitize_filename("Artist/Track"), "Artist-Track")

    def test_generate_m3u8(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            music_root = os.path.join(tmp_dir, "music")
            playlists_dir = os.path.join(music_root, "playlists")
            artist_dir = os.path.join(music_root, "Dua Lipa", "Future Nostalgia")
            os.makedirs(artist_dir, exist_ok=True)

            track1 = os.path.join(artist_dir, "01 - Levitating.opus")
            track2 = os.path.join(artist_dir, "02 - Don't Start Now.opus")
            with open(track1, "w") as f:
                f.write("a")
            with open(track2, "w") as f:
                f.write("b")

            tracks = [
                {"file_path": track1, "title": "Levitating", "artist": "Dua Lipa", "duration": 203},
                {"file_path": track2, "title": "Don't Start Now", "artist": "Dua Lipa", "duration": 183}
            ]

            out_path = PlaylistGenerator.generate_m3u8("My Playlist", tracks, playlists_dir)
            self.assertTrue(os.path.exists(out_path))

            with open(out_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertTrue(content.startswith("#EXTM3U"))
            self.assertIn("#EXTINF:203,Dua Lipa - Levitating", content)
            self.assertIn("../Dua Lipa/Future Nostalgia/01 - Levitating.opus", content)
            self.assertIn("#EXTINF:183,Dua Lipa - Don't Start Now", content)
            self.assertIn("../Dua Lipa/Future Nostalgia/02 - Don't Start Now.opus", content)


if __name__ == "__main__":
    unittest.main()
