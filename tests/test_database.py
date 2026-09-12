"""Unit tests for Database."""

import unittest
import tempfile
import os
from src.database import Database


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_library.db")
        self.db = Database(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_save_and_get_track(self):
        # Create a dummy file
        dummy_file = os.path.join(self.tmp_dir.name, "song.opus")
        with open(dummy_file, "w") as f:
            f.write("dummy audio")

        self.assertFalse(self.db.is_downloaded("video123"))

        self.db.save_track(
            youtube_id="video123",
            file_path=dummy_file,
            title="Cool Song",
            artist="Awesome Band",
            album="Great Album",
            duration=180,
            format_name="opus",
            has_lyrics=True
        )

        self.assertTrue(self.db.is_downloaded("video123"))
        track = self.db.get_track("video123")
        self.assertIsNotNone(track)
        self.assertEqual(track["title"], "Cool Song")
        self.assertEqual(track["artist"], "Awesome Band")
        self.assertEqual(track["has_lyrics"], 1)

    def test_file_missing_resets_is_downloaded(self):
        missing_file = os.path.join(self.tmp_dir.name, "nonexistent.opus")
        self.db.save_track(
            youtube_id="video999",
            file_path=missing_file,
            title="Deleted Song",
            artist="Artist"
        )
        # Should detect that file doesn't exist on disk and return False
        self.assertFalse(self.db.is_downloaded("video999"))

    def test_playlist_tracking(self):
        dummy1 = os.path.join(self.tmp_dir.name, "1.opus")
        dummy2 = os.path.join(self.tmp_dir.name, "2.opus")
        with open(dummy1, "w") as f:
            f.write("a")
        with open(dummy2, "w") as f:
            f.write("b")

        self.db.save_track("id1", dummy1, "Song 1", "Artist A")
        self.db.save_track("id2", dummy2, "Song 2", "Artist B")

        self.db.update_playlist(
            playlist_id="pl_1",
            name="My Playlist",
            url="https://youtube.com/playlist?list=pl_1",
            youtube_ids=["id2", "id1"]  # Note the order: id2 first, then id1
        )

        tracks = self.db.get_playlist_tracks("pl_1")
        self.assertEqual(len(tracks), 2)
        self.assertEqual(tracks[0]["youtube_id"], "id2")
        self.assertEqual(tracks[1]["youtube_id"], "id1")


if __name__ == "__main__":
    unittest.main()
