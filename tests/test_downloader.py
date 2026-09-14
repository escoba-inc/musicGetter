"""Unit tests for downloader module."""

import unittest
import tempfile
import os
from src.downloader import select_best_subtitle_file


class TestDownloaderSubtitles(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.track_dir = self.tmp_dir.name
        self.yt_id = "test_yt_id"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _create_sub(self, lang_code: str) -> str:
        filename = f"{self.yt_id}.{lang_code}.vtt"
        path = os.path.join(self.track_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello\n")
        return path

    def test_select_spanish_over_english_when_preferred(self):
        path_es = self._create_sub("es")
        self._create_sub("en")
        self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*"])
        self.assertEqual(best, path_es)

    def test_select_english_over_spanish_when_preferred(self):
        self._create_sub("es")
        path_en = self._create_sub("en")
        self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["en.*", "es.*"])
        self.assertEqual(best, path_en)

    def test_ignores_german_and_returns_none_if_only_spanish_english_preferred(self):
        # When only German machine-translation exists on YouTube, do not return German!
        self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*"])
        self.assertIsNone(best)

    def test_selects_german_if_explicitly_configured(self):
        path_de = self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*", "de.*"])
        self.assertEqual(best, path_de)

    def test_handles_language_variants_like_latin_american_spanish(self):
        path_es_419 = self._create_sub("es-419")
        self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*"])
        self.assertEqual(best, path_es_419)

    def test_handles_all_keyword_fallback(self):
        path_de = self._create_sub("de")

        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*", "all"])
        self.assertEqual(best, path_de)

    def test_returns_none_when_no_subtitles_exist(self):
        best = select_best_subtitle_file(self.track_dir, self.yt_id, ["es.*", "en.*"])
        self.assertIsNone(best)

    def test_detected_language_overrides_static_preference(self):
        # Song detected as English: should pick English even if preferred_languages has es.* first
        path_es = self._create_sub("es")
        path_en = self._create_sub("en")

        best = select_best_subtitle_file(
            self.track_dir,
            self.yt_id,
            preferred_languages=["es.*", "en.*"],
            detected_language="en"
        )
        self.assertEqual(best, path_en)

    def test_detected_language_spanish_picks_spanish(self):
        path_es = self._create_sub("es")
        path_en = self._create_sub("en")

        best = select_best_subtitle_file(
            self.track_dir,
            self.yt_id,
            preferred_languages=["en.*", "es.*"],
            detected_language="es"
        )
        self.assertEqual(best, path_es)

    def test_detected_language_picks_orig_track(self):
        # YouTube auto-caption orig track
        path_orig = self._create_sub("es-orig")
        self._create_sub("de")

        best = select_best_subtitle_file(
            self.track_dir,
            self.yt_id,
            detected_language="es"
        )
        self.assertEqual(best, path_orig)

    @unittest.mock.patch("src.downloader.requests.get")
    def test_download_channel_avatar_from_og_image(self, mock_get):
        from src.downloader import Downloader

        mock_html_resp = unittest.mock.MagicMock()
        mock_html_resp.status_code = 200
        mock_html_resp.text = '<html><head><meta property="og:image" content="https://yt3.googleusercontent.com/avatar=s900-c-k-c0x00ffffff-no-rj"></head></html>'

        mock_img_resp = unittest.mock.MagicMock()
        mock_img_resp.status_code = 200
        mock_img_resp.content = b"IMAGE_BYTES_12345" * 100

        mock_get.side_effect = [mock_html_resp, mock_img_resp]

        avatar_bytes = Downloader.download_channel_avatar("https://www.youtube.com/@ArtistChannel")
        self.assertIsNotNone(avatar_bytes)
        self.assertEqual(avatar_bytes, b"IMAGE_BYTES_12345" * 100)


if __name__ == "__main__":
    unittest.main()
