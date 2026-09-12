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


if __name__ == "__main__":
    unittest.main()
