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

    def test_orphan_and_stale_playlists(self):
        self.db.save_track("id1", "/path/1.opus", "Track 1", "Artist 1")
        self.db.save_track("id2", "/path/2.opus", "Track 2", "Artist 2")
        self.db.save_track("id3", "/path/3.opus", "Track 3", "Artist 3")

        # PL1 has id1 and id2. PL2 has id2. id3 is in neither.
        self.db.update_playlist("PL1", "Playlist 1", "https://url/1", ["id1", "id2"])
        self.db.update_playlist("PL2", "Playlist 2", "https://url/2", ["id2"])

        # Active playlists: PL1 and PL2. id3 is an orphan.
        orphans = self.db.get_orphan_tracks(["PL1", "PL2"])
        self.assertEqual(len(orphans), 1)
        self.assertEqual(orphans[0]["youtube_id"], "id3")

        # If id1 is removed from PL1 (so only id2 remains in PL1)
        self.db.update_playlist("PL1", "Playlist 1", "https://url/1", ["id2"])
        orphans_after = self.db.get_orphan_tracks(["PL1", "PL2"])
        orphan_ids = [o["youtube_id"] for o in orphans_after]
        self.assertIn("id1", orphan_ids)
        self.assertIn("id3", orphan_ids)
        self.assertNotIn("id2", orphan_ids)  # id2 is still in PL1 and PL2!

        # Stale playlist detection (e.g. if PL1 was removed from config and only PL2 is active)
        stale = self.db.get_stale_playlists(["PL2"])
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["playlist_id"], "PL1")


if __name__ == "__main__":
    unittest.main()
