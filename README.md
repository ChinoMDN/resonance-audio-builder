# Resonance Audio Library Builder

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![CI](https://github.com/ChinoMDN/resonance-audio-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ChinoMDN/resonance-audio-builder/actions)

Build and manage a personal audio library using publicly accessible media sources, enriched with professional metadata, lyrics, and loudness normalization.

---

## Table of Contents

- [Why Resonance?](#why-resonance)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Audio Normalization](#audio-normalization-ebu-r128)
- [Lyrics](#lyrics)
- [Advanced Usage](#advanced-usage)
- [Keyboard Controls](#keyboard-controls)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Contributing](#contributing)
- [License](#license)
- [Legal Notice](#legal-notice)

---

## Why Resonance?

Many personal audio collections suffer from:

- Inconsistent loudness levels across tracks
- Incomplete or inaccurate metadata
- Lack of embedded lyrics
- Poor or inconsistent transcoding quality

Resonance focuses on **library quality and consistency**, providing:

- Professional-grade EBU R128 loudness normalization
- Automatic metadata enrichment from external sources
- Embedded synchronized lyrics support
- A high-quality FFmpeg-based audio processing pipeline

---

## Features

| Feature                    | Description                                                   |
| -------------------------- | ------------------------------------------------------------- |
| **Rich UI**                | Professional terminal interface with live progress            |
| **Spectral Analysis**      | **NEW!** Detects fake HG audio (upscaled 128kbps)             |
| **Watchdog Mode**          | **NEW!** Auto-downloads when you drop CSVs into `Playlists/`  |
| **Metadata Enrichment**    | Title, artist, album, cover art, ISRC (from external sources) |
| **Multi-profile Encoding** | Configurable high and low bitrate audio profiles              |
| **Audio Normalization**    | EBU R128 loudnorm for consistent perceived volume             |
| **Embedded Lyrics**        | Automatic lyrics retrieval and embedding                      |
| **Smart Matching**         | ISRC-based matching with text-search fallback                 |
| **Resume Support**         | Checkpoint-based recovery for interrupted sessions            |
| **Organized Output**       | **NEW!** Auto-sorts lists into subfolders                     |

---

## How to Use

### 1. Prerequisites

- **Python 3.10+** (Recommended)
- **FFmpeg**: Essential for audio processing. [Download here](https://ffmpeg.org/download.html) and ensure it's in your system PATH.

### 2. Installation

```bash
git clone https://github.com/ChinoMDN/resonance-audio-builder.git
cd resonance-audio-builder
pip install -r requirements.txt
```

### 3. Usage Guide

#### Step A: Prepare your tracks

Export your playlist to a **CSV file** and place it in the `Playlists/` directory. Ensure it has at least `Artist` and `Title` columns.

#### Step B: Start the builder

You can run the application in three ways:

1.  **Direct Execution (Windows)**: Double-click `run_app.bat`. This is the easiest way to start.
2.  **Manual CLI**: Run `python run.py`.
3.  **Watchdog Mode**: Run `python run.py --watch`. The program will monitor the `Playlists/` folder and start downloading as soon as you drop a new CSV file there.

#### Step C: Select Quality

Choose between **High Quality (320kbps)**, **Mobile (96kbps)**, or **Both**. The builder will start processing your list immediately.

---

## Configuration

Edit `config.json` to customize behavior:

```json
{
    "output_folder_hq": "Audio_HQ",
    "output_folder_mobile": "Audio_Mobile",
    "quality_hq_bitrate": "320",
    "quality_mobile_bitrate": "96",
    "max_workers": 3,
    "normalize_audio": true,
    "embed_lyrics": true,
    "output_format": "mp3"
}
```

### Configuration Options

| Option                   | Default        | Description                             |
| ------------------------ | -------------- | --------------------------------------- |
| `output_folder_hq`       | `Audio_HQ`     | Folder for high-quality output          |
| `output_folder_mobile`   | `Audio_Mobile` | Folder for low-bitrate output           |
| `quality_hq_bitrate`     | `320`          | Bitrate for HQ profile                  |
| `quality_mobile_bitrate` | `96`           | Bitrate for mobile profile              |
| `max_workers`            | `3`            | Concurrent processing threads           |
| `normalize_audio`        | `true`         | Enable EBU R128 normalization           |
| `embed_lyrics`           | `true`         | Retrieve and embed lyrics               |
| `output_format`          | `mp3`          | Output format: `mp3`, `flac`, or `copy` |
| `rate_limit_delay_min`   | `0.5`          | Minimum delay between requests          |
| `rate_limit_delay_max`   | `2.0`          | Maximum delay between requests          |
| `generate_m3u`           | `true`         | Generate playlist file                  |
| `save_history`           | `true`         | Save session history                    |

---

## Audio Normalization (EBU R128)

When enabled, FFmpeg applies:

```
loudnorm=I=-14:TP=-1.5:LRA=11
```

- **I=-14**: Target integrated loudness (LUFS)
- **TP=-1.5**: True peak ceiling
- **LRA=11**: Controlled loudness range

This ensures consistent perceived volume across the entire library.

---

## Lyrics

Lyrics are retrieved from:

- **LRCLIB** – Synchronized `.lrc` lyrics
- **lyrics.ovh** – Plain text fallback

Lyrics are embedded using standard ID3 tags and are compatible with most players.

---

## Advanced Usage

### Authenticated Requests

Some publicly accessible media sources may rely on session-based access.
Resonance supports optional user-provided cookies to replicate standard browser requests.

### Proxies & OpSec

To use proxies:

1. Create a `proxies.txt` file in the project root.
2. Add proxies (one per line): `protocol://user:pass@ip:port` or `ip:port`.
3. Enable in `config.py` or set `USE_PROXIES = True`.

This feature does not circumvent DRM, paywalls, or restricted content.

---

## Keyboard Controls

| Key      | Action                           |
| -------- | -------------------------------- |
| `P`      | Pause / Resume                   |
| `S`      | Skip current item                |
| `Q`      | Quit gracefully (saves progress) |
| `Ctrl+C` | Force quit                       |

## Project Structure

```
resonance-audio-builder/
├── src/
│   └── resonance_audio_builder/
│       ├── core/           # Config, Builder, State management
│       ├── audio/          # Downloader, Metadata, Analysis (FFmpeg)
│       ├── network/        # Caching, Rate limiting
│       ├── watch/          # Watchdog observer code
│       ├── cli.py          # Entry point
│       └── __main__.py
├── Playlists/              # Input folder for CSVs (Auto-created)
├── tests/
├── pyproject.toml
├── config.json
├── requirements.txt
├── run.py                  # Access point
└── README.md
```

---

## Troubleshooting

| Issue              | Resolution                                                 |
| ------------------ | ---------------------------------------------------------- |
| FFmpeg not found   | Install FFmpeg and ensure it is in PATH                    |
| HTTP 403 Forbidden | Update yt-dlp (`pip install -U yt-dlp`) or refresh cookies |
| HTTP 429           | Reduce concurrency or use proxies                          |
| Empty output       | Check connectivity and dependencies                        |
| Lyrics missing     | Track may not exist in lyric databases                     |

---

## FAQ

**Q: What input formats are supported?**
CSV files containing at least artist and track name columns.

**Q: Can I resume interrupted sessions?**
Yes. Progress is saved automatically.

**Q: Is this cross-platform?**
Yes. The Python version works on Windows, Linux, and macOS.

**Q: How does this compare to spotDL or SpotDown?**
While tools like **spotDL** or **SpotDown** are excellent for quickly mirroring Spotify playlists, **Resonance** is built with a focus on **Library Curation and Audio Consistency**:

- **Source Agnostic**: Works with any CSV export (Spotify, Apple Music, Tidal, etc.), not tied to a single platform.
- **Audio Integrity**: Includes **Spectral Analysis** to detect and reject "Fake HQ" (upscaled) files.
- **Loudness Normalization**: Uses professional **EBU R128** standards so your entire library sounds consistent.
- **OpSec & Stability**: Advanced proxy management and custom yt-dlp configurations to handle recent platform changes more robustly.

**Q: Can I download thousands of songs at once?**
Yes, Resonance is designed for **large-scale library building**:

- **Persistent Progress**: It saves checkpoints every 5 songs. If you close the app or lose connection, it resumes exactly where it left off.
- **SQLite Caching**: Search results are stored in a database, so re-running a list (or retrying failed items) is nearly instant.
- **Dynamic Rate Limiting**: Avoids being banned by automatically pausing and using randomized delays.
- **Efficient Multithreading**: Processes multiple tracks concurrently to maximize your bandwidth.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

- yt-dlp
- FFmpeg
- Mutagen
- Rich
- LRCLIB

---

## Legal Notice

This software is intended for **personal, educational, and research purposes**.

- Users are responsible for ensuring they have the right to access and process any media handled by this tool
- The author does not host, distribute, or provide media content
- No affiliation with Spotify, YouTube, Google, or any other platform is claimed
- This software does not circumvent DRM, paywalls, or access restricted content
- This software does not bypass platform protections
- Use responsibly and in accordance with applicable laws.
