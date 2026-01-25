# Resonance Audio Library Builder

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![yt-dlp](https://img.shields.io/badge/yt--dlp-latest-red.svg)](https://github.com/yt-dlp/yt-dlp)
[![CI](https://github.com/ChinoMDN/resonance-audio-builder/actions/workflows/ci.yml/badge.svg)](https://github.com/ChinoMDN/resonance-audio-builder/actions)

Build and manage a personal audio library using publicly accessible media sources, enriched with professional metadata, lyrics, and loudness normalization.

---

## Table of Contents

* [Why Resonance?](#why-resonance)
* [Features](#features)
* [Quick Start](#quick-start)
* [Configuration](#configuration)
* [Audio Normalization](#audio-normalization-ebu-r128)
* [Lyrics](#lyrics)
* [Advanced Usage](#advanced-usage)
* [Keyboard Controls](#keyboard-controls)
* [Troubleshooting](#troubleshooting)
* [FAQ](#faq)
* [Contributing](#contributing)
* [License](#license)
* [Legal Notice](#legal-notice)

---

## Why Resonance?

Many personal audio collections suffer from:

* Inconsistent loudness levels across tracks
* Incomplete or inaccurate metadata
* Lack of embedded lyrics
* Poor or inconsistent transcoding quality

Resonance focuses on **library quality and consistency**, providing:

* Professional-grade EBU R128 loudness normalization
* Automatic metadata enrichment from external sources
* Embedded synchronized lyrics support
* A high-quality FFmpeg-based audio processing pipeline

---

## Features

| Feature                    | Description                                                   |
| -------------------------- | ------------------------------------------------------------- |
| **Rich UI**                | Professional terminal interface with live progress            |
| **Metadata Enrichment**    | Title, artist, album, cover art, ISRC (from external sources) |
| **Multi-profile Encoding** | Configurable high and low bitrate audio profiles              |
| **Audio Normalization**    | EBU R128 loudnorm for consistent perceived volume             |
| **Embedded Lyrics**        | Automatic lyrics retrieval and embedding                      |
| **Smart Matching**         | ISRC-based matching with text-search fallback                 |
| **Resume Support**         | Checkpoint-based recovery for interrupted sessions            |
| **Rate Limiting**          | Adaptive delays for network stability                         |
| **Real-time Controls**     | Pause, skip, and graceful shutdown                            |

---

## Quick Start

### Prerequisites

* **Python 3.10+**
* **FFmpeg** – Download from [https://ffmpeg.org](https://ffmpeg.org) and add to PATH
* **Deno** (optional) – Used for auxiliary request handling

### Installation

```bash
git clone https://github.com/ChinoMDN/resonance-audio-builder.git
cd resonance-audio-builder
pip install -r requirements.txt
```

### Build Executable (Windows)

Run `build_exe.bat` to generate a standalone executable in the `dist/` directory.

### Usage

1. Export a track list to CSV (e.g. from a music library manager)
2. Place the CSV file in the project root
3. Run:

```bash
python src/library_builder.py
```

4. Follow the interactive menu:

```
+-- Main Menu -------------------------------------------+
|  [1] Process library from CSV                         |
|  [2] Retry failed entries                             |
|  [3] Clear cache/progress                             |
|  [4] Exit                                             |
+-------------------------------------------------------+
```

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

| Option                   | Default            | Description                             |
| ------------------------ | ------------------ | --------------------------------------- |
| `output_folder_hq`       | `Audio_HQ`     | Folder for high-quality output          |
| `output_folder_mobile`   | `Audio_Mobile` | Folder for low-bitrate output           |
| `quality_hq_bitrate`     | `320`              | Bitrate for HQ profile                  |
| `quality_mobile_bitrate` | `96`               | Bitrate for mobile profile              |
| `max_workers`            | `3`                | Concurrent processing threads           |
| `normalize_audio`        | `true`             | Enable EBU R128 normalization           |
| `embed_lyrics`           | `true`             | Retrieve and embed lyrics               |
| `output_format`          | `mp3`              | Output format: `mp3`, `flac`, or `copy` |
| `rate_limit_delay_min`   | `0.5`              | Minimum delay between requests          |
| `rate_limit_delay_max`   | `2.0`              | Maximum delay between requests          |
| `generate_m3u`           | `true`             | Generate playlist file                  |
| `save_history`           | `true`             | Save session history                    |

---

## Audio Normalization (EBU R128)

When enabled, FFmpeg applies:

```
loudnorm=I=-14:TP=-1.5:LRA=11
```

* **I=-14**: Target integrated loudness (LUFS)
* **TP=-1.5**: True peak ceiling
* **LRA=11**: Controlled loudness range

This ensures consistent perceived volume across the entire library.

---

## Lyrics

Lyrics are retrieved from:

* **LRCLIB** – Synchronized `.lrc` lyrics
* **lyrics.ovh** – Plain text fallback

Lyrics are embedded using standard ID3 tags and are compatible with most players.

---

## Advanced Usage

### Authenticated Requests

Some publicly accessible media sources may rely on session-based access.
Resonance supports optional user-provided cookies to replicate standard browser requests.

This feature does not circumvent DRM, paywalls, or restricted content.

Use a dedicated browser profile/account when exporting cookies to reduce risk.

---

## Keyboard Controls

| Key      | Action                           |
| -------- | -------------------------------- |
| `P`      | Pause / Resume                   |
| `S`      | Skip current item                |
| `Q`      | Quit gracefully (saves progress) |
| `Ctrl+C` | Force quit                       |

---

## Project Structure

```
resonance-audio-builder/
├── src/
│   └── library_builder.py
├── config.json
├── requirements.txt
├── setup.py
├── build_exe.bat
├── tests/
├── .github/workflows/
├── dist/
└── README.md
```

---

## Troubleshooting

| Issue                   | Resolution                              |
| ----------------------- | --------------------------------------- |
| FFmpeg not found        | Install FFmpeg and ensure it is in PATH |
| Authentication required | Provide valid cookies                   |
| HTTP 429                | Reduce concurrency                      |
| Empty output            | Check connectivity and dependencies     |
| Lyrics missing          | Track may not exist in lyric databases  |

---

## FAQ

**Q: What input formats are supported?**
CSV files containing at least artist and track name columns.

**Q: Can I resume interrupted sessions?**
Yes. Progress is saved automatically.

**Q: Is this cross-platform?**
Yes. The Python version works on Windows, Linux, and macOS.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## License

This project is licensed under the [MIT License](LICENSE).

---

## Acknowledgments

* yt-dlp
* FFmpeg
* Mutagen
* Rich
* LRCLIB

---

## Legal Notice

This software is intended for **personal, educational, and research purposes**.

* Users are responsible for ensuring they have the right to access and process any media handled by this tool
* The author does not host, distribute, or provide media content
* No affiliation with Spotify, YouTube, Google, or any other platform is claimed
* This software does not circumvent DRM, paywalls, or access restricted content
* This software does not bypass platform protections
* Use responsibly and in accordance with applicable laws.


