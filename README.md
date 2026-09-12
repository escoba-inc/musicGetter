# MusicGetter 🎵

> Automated YouTube & YouTube Music playlist sync engine for **Navidrome**. Downloads clean audio, enriches metadata from official music databases, fetches ultra-high-resolution cover art and synchronized lyrics, deduplicates tracks, and generates native Navidrome playlists.

---

## ✨ Features

- **🎧 Clean Audio Ingestion**: Extracts native Opus (`.opus`) or AAC (`.m4a`) directly from YouTube streams without lossy transcoding, or transcodes to MP3 if preferred.
- **🧹 Smart Title Cleaning**: Automatically strips chaotic video noise (`(Official Video)`, `[MV]`, `[4K]`, `(Lyrics)`, `[Official Audio]`, `Visualizer`, etc.) while carefully preserving legitimate track designations like `(Acoustic)`, `(Live at ...)`, and `(Remix)`.
- **🏷️ Metadata Enrichment (No API Keys Needed)**: Matches tracks against the **iTunes Search API** and **Deezer API** to obtain canonical Track Titles, Artists, Albums, Release Years, and Track Numbers.
- **🖼️ Pristine Album Artwork**: Fetches original high-resolution album covers (up to 3000×3000px). If unavailable, falls back to the YouTube thumbnail automatically cropped to a 1:1 square.
- **🎤 Synchronized Lyrics with Subtitle Fallback**:
  - Primary: Fetches synchronized `.lrc` lyrics from **LRCLIB**.
  - Fallback: Automatically downloads YouTube captions/subtitles and converts them into standard `.lrc` synchronized karaoke timestamps.
  - Both embedded into audio tags and saved as sidecar `.lrc` files (rendered natively by Navidrome and Subsonic apps like Feishin, Symfonium, etc.).
- **🔁 Deduplication & Multi-Playlist Support**: Add as many playlists as you want. Tracks shared between multiple playlists are downloaded once and mapped into Navidrome via `.m3u8` playlist files.
- **📁 Clean Navidrome Organization**: Organizes files into `/music/Artist/Album/01 - Title.opus` with compilation album artist handling (`Various Artists`) so 100 one-track playlist artists don't clutter your Navidrome library view.
- **⏰ Daily Background Sync**: Runs continuously in a Docker container, syncing new playlist additions once daily at your chosen time (e.g. `03:00`), plus immediate sync on startup.
- **🐳 Docker & Permission Ready**: Includes full `PUID`/`PGID` support so downloaded files on Linux, unRAID, Synology, or TrueNAS maintain your host user's permissions.

---

## 🚀 Quick Start

### 1. Clone & Set Up Configuration

```bash
git clone https://github.com/escoba-inc/musicGetter.git
cd musicGetter

# Create directories for config and music
mkdir -p config music

# Copy example configuration
cp config.example.yaml config/config.yaml
```

### 2. Configure Your Playlists

Edit `config/config.yaml` with your preferred editor:

```yaml
playlists:
  - url: "https://music.youtube.com/playlist?list=PLrEnWoR732-B41U5c81p5G5vG17j61oTz"
    name: "Favorite Beats"
  - url: "https://www.youtube.com/playlist?list=PL4fGSIFgk5t2KqZpQo78jB3iS8s5sN1b8"
    name: "Lo-Fi Study"

library_dir: "/music"
data_dir: "/config"

audio:
  format: "opus"       # Options: "opus" (best quality), "m4a", "mp3"

schedule:
  daily_at: "03:00"    # Daily sync time
  sync_on_startup: true
```

### 3. Launch with Docker Compose

Run MusicGetter (and optionally Navidrome) with:

```bash
docker compose up -d
```

Check the logs to watch your tracks being downloaded and enriched:

```bash
docker compose logs -f musicgetter
```

---

## ⚙️ Configuration Reference

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `playlists` | List | `[]` | List of YouTube or YouTube Music playlist URLs. |
| `library_dir` | Path | `"/music"` | Directory where downloaded music files and playlists are saved. |
| `data_dir` | Path | `"/config"` | Directory where the SQLite tracking database (`library.db`) is stored. |
| `audio.format` | String | `"opus"` | Target audio format: `"opus"`, `"m4a"`, or `"mp3"`. |
| `audio.quality` | String | `"best"` | `"best"` for direct stream copy, or `"320"` for MP3. |
| `organization.structure` | String | `"standard"` | `"standard"` (`Artist/Album/Track.ext`) or `"flat"` (`Artist - Track.ext`). |
| `organization.compilation_album_artist` | String | `"Various Artists"` | Fallback `ALBUMARTIST` for varied-artist playlists to avoid Navidrome UI clutter. |
| `organization.generate_m3u8` | Bool | `true` | Generate `.m3u8` playlist files in the playlists directory for Navidrome. |
| `lyrics.enabled` | Bool | `true` | Enable fetching and writing lyrics. |
| `lyrics.save_lrc` | Bool | `true` | Save sidecar `.lrc` file next to each song. |
| `lyrics.use_lrclib` | Bool | `true` | Use LRCLIB database for synced lyrics. |
| `lyrics.use_youtube_subtitles` | Bool | `true` | Fallback to YouTube captions if LRCLIB has no lyrics. |
| `artwork.max_resolution` | Integer | `3000` | Max artwork resolution from iTunes (up to 3000×3000px). |
| `artwork.save_cover_jpg` | Bool | `true` | Save a `cover.jpg` file in each album folder for Navidrome. |
| `schedule.daily_at` | String | `"03:00"` | 24-hour time (`HH:MM`) when the daily sync runs. |
| `cookies_file` | Path | `null` | Optional path to `cookies.txt` if syncing private playlists. |

---

## ⚡ Manual / On-Demand Sync

While the daemon checks every day automatically, you can trigger an instant sync at any time without restarting the container:

```bash
docker exec -it musicgetter python -m src.main --sync-now
```

---

## 🔒 Private & Age-Restricted Playlists

If any of your YouTube playlists are private or require an account login:
1. Export your YouTube cookies using a browser extension (such as *Get cookies.txt LOCALLY*).
2. Save the exported file as `config/cookies.txt`.
3. MusicGetter will automatically detect and authenticate using `cookies.txt`.

---

## 📂 Output Structure for Navidrome

MusicGetter formats your library exactly as Navidrome prefers:

```
/music/
├── playlists/
│   ├── Favorite Beats.m3u8
│   └── Lo-Fi Study.m3u8
├── Dua Lipa/
│   └── Future Nostalgia/
│       ├── 05 - Levitating.opus
│       ├── 05 - Levitating.lrc
│       └── cover.jpg
└── The Weeknd/
    └── After Hours/
        ├── 09 - Blinding Lights.opus
        ├── 09 - Blinding Lights.lrc
        └── cover.jpg
```

---

## 🧪 Running Tests

To run the full unit test suite:

```bash
python3 -m unittest discover -s tests
```
