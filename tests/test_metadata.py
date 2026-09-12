"""Unit tests for MetadataEnricher."""

import unittest
from unittest.mock import patch, MagicMock
from PIL import Image
import io

from src.cleaner import CleanMetadata
from src.metadata import MetadataEnricher


class TestMetadataEnricher(unittest.TestCase):
    def test_process_youtube_thumbnail(self):
        # Create a 16:9 thumbnail
        img = Image.new("RGB", (1280, 720), color=(50, 100, 150))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        raw_bytes = buf.getvalue()

        processed = MetadataEnricher.process_youtube_thumbnail(raw_bytes)
        self.assertIsNotNone(processed)

        res_img = Image.open(io.BytesIO(processed))
        self.assertEqual(res_img.size, (720, 720), "Expected 1:1 square crop")

    @patch("src.metadata.requests.get")
    def test_query_itunes_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "trackName": "Levitating",
                    "artistName": "Dua Lipa",
                    "collectionName": "Future Nostalgia",
                    "trackNumber": 5,
                    "releaseDate": "2020-03-27T07:00:00Z",
                    "primaryGenreName": "Pop",
                    "artworkUrl100": "https://is1-ssl.mzstatic.com/image/thumb/Music115/v4/.../100x100bb.jpg",
                    "trackTimeMillis": 203000
                }
            ]
        }
        mock_art_resp = MagicMock()
        mock_art_resp.status_code = 200
        mock_art_resp.content = b"fake_artwork_data_over_1000_bytes_" + b"0" * 1200

        mock_get.side_effect = [mock_resp, mock_art_resp]

        meta = CleanMetadata(raw_title="Dua Lipa - Levitating", cleaned_title="Levitating", artist="Dua Lipa")
        enriched = MetadataEnricher.query_itunes(meta, duration=203)

        self.assertIsNotNone(enriched)
        self.assertEqual(enriched.title, "Levitating")
        self.assertEqual(enriched.artist, "Dua Lipa")
        self.assertEqual(enriched.album, "Future Nostalgia")
        self.assertEqual(enriched.year, 2020)
        self.assertEqual(enriched.track_number, 5)
        self.assertEqual(enriched.source, "itunes")
        self.assertIsNotNone(enriched.artwork_bytes)

    @patch("src.metadata.MetadataEnricher.query_itunes")
    @patch("src.metadata.MetadataEnricher.query_deezer")
    def test_enrich_fallback_to_youtube(self, mock_deezer, mock_itunes):
        mock_itunes.return_value = None
        mock_deezer.return_value = None

        img = Image.new("RGB", (640, 480), color=(10, 20, 30))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")

        meta = CleanMetadata(raw_title="Obscure Indie Song", cleaned_title="Obscure Indie Song", artist="Indie Band")
        enriched = MetadataEnricher.enrich(meta, raw_thumbnail_bytes=buf.getvalue())

        self.assertIsNotNone(enriched)
        self.assertEqual(enriched.title, "Obscure Indie Song")
        self.assertEqual(enriched.artist, "Indie Band")
        self.assertEqual(enriched.album, "Singles")
        self.assertEqual(enriched.source, "youtube")
        self.assertIsNotNone(enriched.artwork_bytes)


if __name__ == "__main__":
    unittest.main()
