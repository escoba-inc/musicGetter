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
- **🐳 Docker Ready**: Deploy instantly with standard `docker compose up -d` with zero complex setup.

---

## 🚀 Quick Start (All in `docker-compose.yml`)

No separate configuration files required! You can configure your playlists and settings directly inside `docker-compose.yml`:

### 1. Clone the Repository

```bash
git clone https://github.com/escoba-inc/musicGetter.git
cd musicGetter
```

### 2. Configure & Run in `docker-compose.yml`

Edit `docker-compose.yml` to set your playlist URLs:

```yaml
services:
  musicgetter:
    build: .
    container_name: musicgetter
    restart: unless-stopped
    environment:
      # 🎵 Add as many playlists as you want (URL or URL | Custom Name):
      - PLAYLIST_1=https://music.youtube.com/playlist?list=PLrEnWoR732-B41U5c81p5G5vG17j61oTz | Favorite Beats
      - PLAYLIST_2=https://www.youtube.com/playlist?list=PL4fGSIFgk5t2KqZpQo78jB3iS8s5sN1b8 | Lo-Fi Chill
      # ⚙️ Settings:
      - AUDIO_FORMAT=opus         # "opus" (best quality), "m4a", or "mp3"
      - DAILY_AT=03:00            # Daily check time (24-hour format)
      - SYNC_ON_STARTUP=true      # Sync immediately on startup
    volumes:
      - ./music:/music            # Music folder shared with Navidrome
      - ./config:/config          # Stores database and optional cookies.txt
```

### 3. Launch the Stack

```bash
docker compose up -d
```

View the live sync logs:

```bash
docker compose logs -f musicgetter
```

---

## ⚙️ Configuration Reference (Environment Variables)

All options can be defined directly under `environment:` in `docker-compose.yml`:

| Environment Variable | Default | Description |
| :--- | :--- | :--- |
| `PLAYLIST_1`, `PLAYLIST_2`, ... | `""` | Add numbered playlist URLs: `URL` or `URL \| Custom Name`. |
| `PLAYLISTS` | `""` | Alternatively, multiline or comma-separated list of playlist URLs. |
| `AUDIO_FORMAT` | `"opus"` | Target audio format: `"opus"`, `"m4a"`, or `"mp3"`. |
| `DAILY_AT` | `"03:00"` | Daily time (`HH:MM`) when the automatic sync runs. |
| `SYNC_ON_STARTUP` | `"true"` | Check and download new songs as soon as the container boots. |
| `CLEANUP_REMOVED_TRACKS` | `"true"` | Automatically delete audio files, .lrc sidecars, and empty folders when removed from all playlists. |
| `LYRICS_ENABLED` | `"true"` | Enable fetching and writing lyrics. |
| `SAVE_LRC` | `"true"` | Save sidecar `.lrc` files for Navidrome synced karaoke lyrics. |
| `USE_LRCLIB` | `"true"` | Query LRCLIB for synced lyrics. |
| `USE_YOUTUBE_SUBTITLES` | `"true"` | Fallback to YouTube auto-captions if LRCLIB doesn't have lyrics. |
| `COVER_RESOLUTION` | `"3000"` | Max artwork resolution from iTunes (up to 3000×3000px). |
| `SAVE_COVER_JPG` | `"true"` | Save `cover.jpg` in album folders for Navidrome. |
| `COMPILATION_ALBUM_ARTIST` | `"Various Artists"` | Album Artist tag for playlist tracks to keep Navidrome's Artists tab clean. |
| `STRUCTURE` | `"standard"` | `"standard"` (`Artist/Album/Track.ext`) or `"flat"`. |
| `PUID` / `PGID` | *(optional)* | Optional host user/group ID if you run specialized NAS permissions. |

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
│   └── Lo-Fi Chill.m3u8
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
