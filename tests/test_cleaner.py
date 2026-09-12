"""Unit tests for TitleCleaner."""

import unittest
from src.cleaner import TitleCleaner


class TestTitleCleaner(unittest.TestCase):
    def test_strip_junk_tags(self):
        cases = [
            ("Dua Lipa - Levitating (Official Music Video)", "Dua Lipa - Levitating"),
            ("The Weeknd - Blinding Lights (Official Audio)", "The Weeknd - Blinding Lights"),
            ("Queen – Bohemian Rhapsody (Official Video Remastered)", "Queen – Bohemian Rhapsody"),
            ("Radiohead - Creep [Official Music Video 4K]", "Radiohead - Creep"),
            ("Coldplay - Yellow (Official HD Video)", "Coldplay - Yellow"),
            ("Eminem - Stan (Long Version) ft. Dido", "Eminem - Stan (Long Version) ft. Dido"),
            ("[MV] IU(아이유) - Celebrity", "IU(아이유) - Celebrity"),
            ("Taylor Swift - Anti-Hero (Lyric Video)", "Taylor Swift - Anti-Hero"),
            ("Billie Eilish - bad guy (Visualizer)", "Billie Eilish - bad guy"),
            ("Adele - Easy On Me | Official Video", "Adele - Easy On Me"),
            ("Bad Bunny - Tití Me Preguntó (Video Oficial)", "Bad Bunny - Tití Me Preguntó"),
            ("01. Linkin Park - In The End", "Linkin Park - In The End"),
            ("Juice WRLD - Lucid Dreams (Prod. Nick Mira) [Official Video]", "Juice WRLD - Lucid Dreams"),
        ]
        for raw, expected in cases:
            cleaned = TitleCleaner.strip_junk(raw)
            self.assertEqual(cleaned, expected, f"Failed for: {raw}")

    def test_parse_artist_and_title(self):
        cases = [
            (
                "Dua Lipa - Levitating (Official Music Video)",
                "Dua Lipa",
                "Dua Lipa",
                "Levitating",
            ),
            (
                "The Weeknd - Save Your Tears [Official Audio]",
                "The Weeknd VEVO",
                "The Weeknd",
                "Save Your Tears",
            ),
            (
                "Imagine Dragons - Believer (Lyrics)",
                "ImagineDragons",
                "Imagine Dragons",
                "Believer",
            ),
            (
                "Ed Sheeran - Bad Habits [Official Video]",
                "Ed Sheeran",
                "Ed Sheeran",
                "Bad Habits",
            ),
            (
                "Linkin Park - In The End (Official HD Video)",
                "Linkin Park",
                "Linkin Park",
                "In The End",
            ),
            (
                "Song Without Hyphen (Official Video)",
                "Cool Artist - Topic",
                "Cool Artist",
                "Song Without Hyphen",
            ),
            (
                "Artist - Song Title feat. Guest Singer",
                "RecordLabel",
                "Artist",
                "Song Title (feat. Guest Singer)",
            ),
        ]
        for video_title, channel, exp_artist, exp_title in cases:
            meta = TitleCleaner.parse_artist_and_title(video_title, channel)
            self.assertEqual(meta.artist, exp_artist, f"Artist mismatch for {video_title}")
            self.assertEqual(meta.cleaned_title, exp_title, f"Title mismatch for {video_title}")

    def test_yt_music_native_tags(self):
        meta = TitleCleaner.parse_artist_and_title(
            video_title="Some Raw Video Title",
            channel_name="Original Channel",
            yt_track="Official Track Name",
            yt_artist="Official Artist - Topic"
        )
        self.assertEqual(meta.artist, "Official Artist")
        self.assertEqual(meta.cleaned_title, "Official Track Name")

    def test_preserves_legitimate_parentheses(self):
        # Should keep (Acoustic), (Live), (Remix)
        cases = [
            ("Nirvana - Come As You Are (Acoustic)", "Come As You Are (Acoustic)"),
            ("Daft Punk - One More Time (12\" Mix)", "One More Time (12\" Mix)"),
            ("Oasis - Wonderwall (Live at Knebworth)", "Wonderwall (Live at Knebworth)"),
            ("MGMT - Kids (Soulwax Remix)", "Kids (Soulwax Remix)"),
        ]
        for raw, exp_title in cases:
            meta = TitleCleaner.parse_artist_and_title(raw, "Channel")
            self.assertEqual(meta.cleaned_title, exp_title)

    def test_extract_primary_artist(self):
        cases = [
            ("DePol, Pol Gutierrez Molina", "DePol", "Pol Gutierrez Molina"),
            ("Jim Yosef & Scarlett", "Jim Yosef", "Scarlett"),
            ("Wuicho kun & Andie Gago", "Wuicho kun", "Andie Gago"),
            ("David Guetta x Bebe Rexha", "David Guetta", "Bebe Rexha"),
            ("Marshmello feat. Khalid", "Marshmello", "Khalid"),
            ("Aimee Carty", "Aimee Carty", None),
            ("Fito y Fitipaldis", "Fito y Fitipaldis", None),
            ("Bob Marley & The Wailers", "Bob Marley & The Wailers", None),
            ("Simon & Garfunkel", "Simon & Garfunkel", None),
            ("Tyler, The Creator", "Tyler, The Creator", None),
        ]
        for raw, exp_primary, exp_collab in cases:
            prim, collab = TitleCleaner.extract_primary_artist(raw)
            self.assertEqual(prim, exp_primary, f"Primary mismatch for: {raw}")
            self.assertEqual(collab, exp_collab, f"Collab mismatch for: {raw}")

    def test_multi_artist_title_and_tags(self):
        # yt-music tags with multiple artists
        meta = TitleCleaner.parse_artist_and_title(
            video_title="Quiero Decirte",
            channel_name="DePol",
            yt_track="Quiero Decirte",
            yt_artist="DePol, Pol Gutierrez Molina"
        )
        self.assertEqual(meta.artist, "DePol")
        self.assertEqual(meta.album_artist, "DePol")
        self.assertEqual(meta.cleaned_title, "Quiero Decirte (feat. Pol Gutierrez Molina)")

        # Raw video title with &
        meta2 = TitleCleaner.parse_artist_and_title(
            video_title="Jim Yosef & Scarlett - Volcano [NCS Release]",
            channel_name="NoCopyrightSounds"
        )
        self.assertEqual(meta2.artist, "Jim Yosef")
        self.assertEqual(meta2.album_artist, "Jim Yosef")
        self.assertEqual(meta2.cleaned_title, "Volcano (feat. Scarlett)")


if __name__ == "__main__":
    unittest.main()
