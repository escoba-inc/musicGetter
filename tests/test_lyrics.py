"""Unit tests for LyricsManager."""

import unittest
import tempfile
import os
from src.lyrics import LyricsManager


class TestLyricsManager(unittest.TestCase):
    def test_vtt_timestamp_to_lrc(self):
        self.assertEqual(LyricsManager._vtt_timestamp_to_lrc("00:01:23.456"), "[01:23.45]")
        self.assertEqual(LyricsManager._vtt_timestamp_to_lrc("01:05:12.789"), "[65:12.78]")
        self.assertEqual(LyricsManager._vtt_timestamp_to_lrc("02:15.100"), "[02:15.10]")

    def test_parse_vtt_to_lrc(self):
        vtt = """WEBVTT
Kind: captions
Language: en

00:00:01.000 --> 00:00:04.000
First line of lyrics

00:00:04.000 --> 00:00:07.500
<c>Second</c> line <c.colorE5E5E5>with styling</c>

00:00:07.500 --> 00:00:09.000
[Music]

00:00:09.000 --> 00:00:12.000
Third line here
"""
        res = LyricsManager.parse_vtt_to_lrc(vtt)
        self.assertIsNotNone(res)
        self.assertEqual(res.source, "youtube_subtitles")
        self.assertIn("[00:01.00] First line of lyrics", res.synced_lyrics)
        self.assertIn("[00:04.00] Second line with styling", res.synced_lyrics)
        self.assertNotIn("[Music]", res.synced_lyrics)
        self.assertIn("[00:09.00] Third line here", res.synced_lyrics)

    def test_save_lrc_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            audio_path = os.path.join(tmp_dir, "song.opus")
            with open(audio_path, "w") as f:
                f.write("audio")

            lyrics_content = "[00:01.00] Hello\n[00:05.00] World"
            saved_path = LyricsManager.save_lrc_file(audio_path, lyrics_content)

            self.assertTrue(os.path.exists(saved_path))
            self.assertEqual(saved_path, os.path.join(tmp_dir, "song.lrc"))
            with open(saved_path, "r") as f:
                self.assertEqual(f.read().strip(), lyrics_content)


    @unittest.mock.patch("src.lyrics.requests.get")
    def test_fetch_from_lrclib(self, mock_get):
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "syncedLyrics": "[00:10.00] Line from LRCLIB",
            "plainLyrics": "Line from LRCLIB",
            "duration": 180
        }
        mock_get.return_value = mock_resp

        res = LyricsManager.fetch_from_lrclib("Song", "Artist", duration=180)
        self.assertIsNotNone(res)
        self.assertEqual(res.source, "lrclib")
        self.assertEqual(res.synced_lyrics, "[00:10.00] Line from LRCLIB")

    @unittest.mock.patch("src.lyrics.requests.get")
    def test_fetch_from_lrclib_duration_mismatch(self, mock_get):
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        # Track duration on YouTube is 180s, but LRCLIB returns version of 210s (e.g. music video intro)
        mock_resp.json.return_value = {
            "syncedLyrics": "[00:10.00] Line from LRCLIB",
            "plainLyrics": "Line from LRCLIB",
            "duration": 210
        }
        mock_get.return_value = mock_resp

        res = LyricsManager.fetch_from_lrclib("Song", "Artist", duration=180)
        self.assertIsNotNone(res)
        # Synced lyrics should be rejected due to > 4s duration mismatch!
        self.assertIsNone(res.synced_lyrics)
        self.assertEqual(res.plain_lyrics, "Line from LRCLIB")

    @unittest.mock.patch("src.lyrics.LyricsManager.fetch_from_lrclib")
    def test_get_lyrics_prioritizes_youtube_subtitles_over_lrclib_synced(self, mock_lrclib):
        # Even when LRCLIB has synced lyrics, YouTube subtitles must take precedence!
        mock_lrclib.return_value = unittest.mock.MagicMock(
            synced_lyrics="[00:05.00] LRCLIB Studio Lyrics",
            plain_lyrics="LRCLIB Studio Lyrics",
            source="lrclib"
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            vtt_file = os.path.join(tmp_dir, "sub.vtt")
            with open(vtt_file, "w") as f:
                f.write("WEBVTT\n\n00:00:02.000 --> 00:00:05.000\nExact Video Subtitle Line\n")

            res = LyricsManager.get_lyrics(
                title="Song",
                artist="Artist",
                duration=180,
                vtt_subtitle_path=vtt_file,
                use_lrclib=True,
                use_yt_subs=True
            )
            self.assertIsNotNone(res.synced_lyrics)
            self.assertEqual(res.source, "youtube_subtitles")
            self.assertIn("[00:02.00] Exact Video Subtitle Line", res.synced_lyrics)


    @unittest.mock.patch("src.lyrics.requests.get")
    def test_fetch_from_lyricsovh(self, mock_get):
        mock_resp = unittest.mock.MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "lyrics": "Quién diría que me gustarías\nEl mismo día..."
        }
        mock_get.return_value = mock_resp

        res = LyricsManager.fetch_from_lyricsovh("Quién Diría", "DePol")
        self.assertIsNotNone(res)
        self.assertEqual(res.source, "lyrics_ovh")
        self.assertIn("Quién diría", res.plain_lyrics)

    @unittest.mock.patch("src.lyrics.LyricsManager.fetch_from_lrclib")
    @unittest.mock.patch("src.lyrics.LyricsManager.fetch_from_lyricsovh")
    def test_get_lyrics_tier4_lyricsovh(self, mock_ovh, mock_lrclib):
        mock_lrclib.return_value = None
        mock_ovh.return_value = unittest.mock.MagicMock(
            synced_lyrics=None,
            plain_lyrics="Plain lyrics from lyrics.ovh",
            source="lyrics_ovh"
        )

        res = LyricsManager.get_lyrics("Song", "Artist", use_lrclib=True, use_yt_subs=False)
        self.assertIsNotNone(res)
        self.assertEqual(res.source, "lyrics_ovh")
        self.assertEqual(res.plain_lyrics, "Plain lyrics from lyrics.ovh")


if __name__ == "__main__":
    unittest.main()
