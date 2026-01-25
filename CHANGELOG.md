# Changelog

All notable changes to this project will be documented in this file.

The format follows **[Keep a Changelog](https://keepachangelog.com/en/1.0.0/)**
This project adheres to **[Semantic Versioning](https://semver.org/spec/v2.0.0.html)**.

---

## [7.0.1] – 2026-01-25

### Fixed

- **Downloader Stability:** Fixed logic error where search results weren't correctly passed to the downloader.
- **YouTube Compatibility:** Mitigated `HTTP 403 Forbidden` errors by implementing enhanced `yt-dlp` arguments (`player_client`, `po_token`) and headers.
- **Audio Analysis:** Fixed `NameError` and argument mismatch in spectral analyzer.
- **Temp File Management:** Reverted raw downloads to the system's temporary directory for a cleaner workspace.
- **Metadata Consistency:** Removed redundant metadata injection in the management layer.

---

## [7.0.0] – 2026-01-24

### Added

- **Spectral Analysis:** Automatic integrity check to detect "fake" 320kbps files (upscaled 128kbps) using FFmpeg.
- **Watchdog Mode:** New `--watch` flag to monitor the `Playlists/` directory and auto-start downloads when CSVs are added.
- **Playlist Organization:**
    - Dedicated `Playlists/` input directory.
    - Output files are now organized into subfolders matching the CSV filename (e.g., `Audio_HQ/MyPlaylist/Song.mp3`).
- **Multi-CSV Support:** Ability to process all CSV files in the input directory at once from the menu.
- **Proxy/OpSec Support:** Centralized `ProxyManager` reading from `proxies.txt` to rotate IPs for YouTube searches and downloads.
- **Configurable Input:** Added `INPUT_FOLDER`, `PROXIES_FILE`, and `USE_PROXIES` settings in `config.py`.

### Changed

- **Modular Architecture:** Complete refactor from monolithic `library_builder.py` to a domain-driven `core/`, `audio/`, `network/`, `watch/` package structure.
- **CLI improvements:** Streamlined menu and quality selection for batch processing.
- **Dependencies:** Added `watchdog` to `requirements.txt`.

---

## [6.0.0] – 2026-01-24

### Added

- Modern Python packaging with `pyproject.toml` (PEP 517/518)
- Proper package structure (`src/resonance_audio_builder/`)
- Module entry point (`python -m resonance_audio_builder`)
- CLI entry point (`resonance-audio-builder` command)
- Rich terminal UI with live progress tracking
- Code formatting with Black and isort
- Type hints and mypy configuration
- Comprehensive test suite (27 tests)
- **Metadata Injection:** Full ID3 tag support including Cover Art
- **Enhanced Cleanup:** "Clear All" option now thoroughly removes cache and history

### Fixed

- **Deadlock:** Fixed application hang when clearing cache (Menu option 3)
- **Cleanup:** Fixed "Clear All" not deleting all data files (history, playlists)
- **Stability:** Improved thread safety in progress tracker using `RLock`

### Changed

- Migrated from `setup.py` to `pyproject.toml`
- Restructured source code into proper Python package
- Updated CI/CD pipeline with multi-platform testing
- Improved code formatting and style consistency
- Updated Docker configuration for new package structure

### Removed

- Legacy `setup.py` (replaced by `pyproject.toml`)
- Old flat file structure

---

## [5.0.0] – 2024-01-24

### Added

- External configuration file (`config.json`)
- Adaptive rate limiting for network stability
- Visual ASCII-based progress indicators
- File integrity verification using MD5 hashes
- Automatic M3U playlist generation
- Persistent session history tracking
- Optional Deno-based request handling for restricted content
- Embedded synchronized and plain lyrics support

### Changed

- Complete UI redesign using structured ASCII layouts
- Refactored error handling with typed exceptions
- Improved CSV encoding auto-detection and normalization
- Internal storage migration from JSON to SQLite
- Modularization of audio processing pipeline

### Fixed

- Edge cases in interrupted download recovery
- Metadata mismatches caused by inconsistent CSV headers

---

## [4.2.0] – 2024-01-23

### Added

- Real-time keyboard controls:
    - `P` – Pause / Resume
    - `S` – Skip current item
    - `Q` – Graceful shutdown

- Menu option to retry failed items
- ETA calculation based on rolling averages

### Changed

- Replaced emoji-based UI elements with ASCII for cross-platform compatibility
- Improved progress reporting under multi-threaded workloads

---

## [4.1.0] – 2024-01-22

### Added

- Interactive main menu system
- Cache and progress cleanup options
- System status and diagnostics panel

### Fixed

- Validation of `cookies.txt` before authenticated requests
- Incorrect resume behavior after forced termination

---

## [4.0.0] – 2024-01-21

### Added

- Quality selection modes:
    - High Quality only
    - Mobile Quality only
    - Dual output

- Automatic CSV file discovery in project directory
- Robust CSV encoding detection:
    - UTF-8 (with and without BOM)
    - Latin-1
    - CP1252

- CSV header normalization for improved compatibility

### Changed

- Improved handling of malformed or partial CSV exports

---

## [3.0.0] – 2024-01-20

### Added

- Multi-threaded download and processing pipeline
- Search result caching with TTL
- Atomic checkpoint persistence
- Cover art embedding
- ID3 metadata tagging support

### Changed

- Migration to a cleaner, layered architecture
- Introduction of typed domain-specific exceptions

---

## [2.x] – Initial Development

### Added

- Proof-of-concept audio retrieval
- Basic metadata tagging
- Single-threaded processing pipeline
