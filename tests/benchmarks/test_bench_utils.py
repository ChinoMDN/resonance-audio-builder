"""Benchmarks for utility functions and state management."""

import os
from unittest.mock import MagicMock

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.state import ProgressDB
from resonance_audio_builder.core.utils import calculate_md5, export_m3u


# ---------------------------------------------------------------------------
# MD5 hashing benchmarks
# ---------------------------------------------------------------------------
class TestMD5Benchmarks:
    """Benchmarks for file MD5 hash calculation."""

    @pytest.fixture
    def small_file(self, tmp_path):
        """4 KB file — typical very short audio snippet."""
        p = tmp_path / "small.bin"
        p.write_bytes(os.urandom(4 * 1024))
        return p

    @pytest.fixture
    def medium_file(self, tmp_path):
        """1 MB file — typical compressed audio."""
        p = tmp_path / "medium.bin"
        p.write_bytes(os.urandom(1024 * 1024))
        return p

    @pytest.fixture
    def large_file(self, tmp_path):
        """10 MB file — typical HQ audio."""
        p = tmp_path / "large.bin"
        p.write_bytes(os.urandom(10 * 1024 * 1024))
        return p

    def test_md5_small_file(self, benchmark, small_file):
        """Benchmark: MD5 of 4 KB file."""
        benchmark(calculate_md5, small_file)

    def test_md5_medium_file(self, benchmark, medium_file):
        """Benchmark: MD5 of 1 MB file."""
        benchmark(calculate_md5, medium_file)

    def test_md5_large_file(self, benchmark, large_file):
        """Benchmark: MD5 of 10 MB file."""
        benchmark(calculate_md5, large_file)


# ---------------------------------------------------------------------------
# M3U export benchmarks
# ---------------------------------------------------------------------------
class TestM3UExportBenchmarks:
    """Benchmarks for M3U playlist file generation."""

    def _make_tracks(self, count: int):
        return [(f"subfolder/Artist - Track {i}.m4a", f"Artist - Track {i}", 240) for i in range(count)]

    def test_export_m3u_25_tracks(self, benchmark, tmp_path):
        """Benchmark: Generate M3U with 25 tracks."""
        tracks = self._make_tracks(25)
        filepath = str(tmp_path / "playlist.m3u")
        benchmark(export_m3u, tracks, filepath)

    def test_export_m3u_100_tracks(self, benchmark, tmp_path):
        """Benchmark: Generate M3U with 100 tracks."""
        tracks = self._make_tracks(100)
        filepath = str(tmp_path / "playlist.m3u")
        benchmark(export_m3u, tracks, filepath)

    def test_export_m3u_500_tracks(self, benchmark, tmp_path):
        """Benchmark: Generate M3U with 500 tracks (large library)."""
        tracks = self._make_tracks(500)
        filepath = str(tmp_path / "playlist.m3u")
        benchmark(export_m3u, tracks, filepath)


# ---------------------------------------------------------------------------
# SQLite ProgressDB benchmarks
# ---------------------------------------------------------------------------
class TestProgressDBBenchmarks:
    """Benchmarks for SQLite-backed progress tracking."""

    @pytest.fixture
    def db(self, tmp_path):
        cfg = MagicMock(spec=Config)
        cfg.CHECKPOINT_FILE = str(tmp_path / "progress.json")
        return ProgressDB(cfg)

    @pytest.fixture
    def sample_track(self):
        return TrackMetadata(
            track_id="isrc_USQX91300108",
            title="Get Lucky",
            artist="Daft Punk",
            isrc="USQX91300108",
        )

    def test_mark_success(self, benchmark, db, sample_track):
        """Benchmark: Mark a track as successfully downloaded."""
        benchmark(db.mark, sample_track, "ok", 5_000_000)

    def test_mark_error(self, benchmark, db, sample_track):
        """Benchmark: Mark a track as failed."""
        benchmark(db.mark, sample_track, "error", 0, "Download timeout")

    def test_is_done_lookup(self, benchmark, db, sample_track):
        """Benchmark: Check if a track is done (after marking)."""
        db.mark(sample_track, "ok", 5_000_000)
        benchmark(db.is_done, sample_track.track_id)

    def test_get_stats(self, benchmark, db, sample_track):
        """Benchmark: Get aggregate stats from DB with some data."""
        # Pre-populate with 50 records
        for i in range(50):
            t = TrackMetadata(track_id=f"track_{i}", title=f"Track {i}", artist="Artist")
            db.mark(t, "ok" if i % 3 != 0 else "error", 1_000_000)
        benchmark(db.get_stats)

    def test_get_failed_tracks(self, benchmark, db):
        """Benchmark: Retrieve failed tracks eligible for retry."""
        # Pre-populate with 20 failures
        for i in range(20):
            t = TrackMetadata(track_id=f"fail_{i}", title=f"Failed {i}", artist="Artist")
            db.mark(t, "error", 0, f"Error {i}")
        benchmark(db.get_failed_tracks, 3)


# ---------------------------------------------------------------------------
# Config loading benchmarks
# ---------------------------------------------------------------------------
class TestConfigBenchmarks:
    """Benchmarks for Config loading."""

    def test_config_default_creation(self, benchmark):
        """Benchmark: Create Config with default values."""
        benchmark(Config)

    def test_config_load_nonexistent(self, benchmark, tmp_path):
        """Benchmark: Load config from non-existent file (fallback to defaults)."""
        benchmark(Config.load, str(tmp_path / "nonexistent.json"))

    def test_config_load_from_file(self, benchmark, tmp_path):
        """Benchmark: Load config from a real JSON file."""
        import json

        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "max_workers": 5,
                    "max_retries": 5,
                    "quality_hq_bitrate": "320",
                    "quality_mobile_bitrate": "128",
                    "debug_mode": False,
                    "generate_m3u": True,
                    "save_history": True,
                }
            ),
            encoding="utf-8",
        )
        benchmark(Config.load, str(config_path))
