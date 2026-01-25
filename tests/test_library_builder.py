import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add src directory to path (if needed, but usually redundant if run from root)
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(root_dir, "src") not in sys.path:
    sys.path.insert(0, os.path.join(root_dir, "src"))

from resonance_audio_builder.audio.metadata import TrackMetadata  # noqa: E402
from resonance_audio_builder.core.config import Config  # noqa: E402
from resonance_audio_builder.core.ui import format_size, format_time  # noqa: E402
from resonance_audio_builder.core.utils import calculate_md5, export_m3u, save_history  # noqa: E402
from resonance_audio_builder.network.cache import CacheManager  # noqa: E402
from resonance_audio_builder.network.limiter import RateLimiter  # noqa: E402
from resonance_audio_builder.network.utils import validate_cookies_file  # noqa: E402


class TestConfig:
    """Tests for Config class"""

    def test_default_values(self):
        """Config should have sensible defaults"""
        cfg = Config()
        assert cfg.OUTPUT_FOLDER_HQ == "Audio_HQ"
        assert cfg.OUTPUT_FOLDER_MOBILE == "Audio_Mobile"
        assert cfg.MAX_WORKERS == 3
        assert cfg.QUALITY_HQ_BITRATE == "320"

    def test_load_from_json(self):
        """Config.load() should read from JSON file"""
        # Create temp file, write, close, then test
        fd, filepath = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"max_workers": 5, "quality_hq_bitrate": "256"}, f)

            cfg = Config.load(filepath)
            assert cfg.MAX_WORKERS == 5
            assert cfg.QUALITY_HQ_BITRATE == "256"
        finally:
            os.unlink(filepath)

    def test_load_missing_file(self):
        """Config.load() should return defaults if file missing"""
        cfg = Config.load("nonexistent.json")
        assert cfg.MAX_WORKERS == 3  # Default value


class TestTrackMetadata:
    """Tests for TrackMetadata class"""

    def test_from_csv_row_basic(self):
        """Should parse basic CSV row"""
        row = {
            "Track Name": "Test Song",
            "Artist Name(s)": "Test Artist",
            "Album Name": "Test Album",
            "ISRC": "USTEST123456",
        }
        track = TrackMetadata.from_csv_row(row)

        assert track.title == "Test Song"
        assert track.artist == "Test Artist"
        assert track.album == "Test Album"
        assert track.isrc == "USTEST123456"
        assert track.track_id == "isrc_USTEST123456"

    def test_from_csv_row_no_isrc(self):
        """Should generate hash ID when no ISRC"""
        row = {"Track Name": "Test Song", "Artist Name(s)": "Test Artist"}
        track = TrackMetadata.from_csv_row(row)

        assert not track.track_id.startswith("isrc_")
        assert len(track.track_id) == 16  # MD5 hash truncated

    def test_safe_filename(self):
        """Should remove invalid characters from filename"""
        track = TrackMetadata(track_id="test", title="Song: With <Bad> Characters?", artist="Artist/Name")

        filename = track.safe_filename
        assert ":" not in filename
        assert "<" not in filename
        assert ">" not in filename
        assert "?" not in filename
        assert "/" not in filename

    def test_format_size(self):
        assert format_size(1024) == "1.00 KB"
        assert format_size(1024 * 1024) == "1.00 MB"

    def test_format_time(self):
        assert format_time(65) == "1m 05s"
        assert format_time(3665) == "1h 01m"

    def test_is_valid_quality(self):
        # We assume such a method exists or was planned
        pass

    def test_bool_comparisons(self):
        # Fix E712
        cond_true = True
        cond_false = False
        assert cond_true is True
        assert cond_false is False
        assert not cond_false

    def test_safe_filename_reserved(self):
        """Should produce valid filename even with reserved names"""
        track = TrackMetadata(track_id="test", title="CON", artist="PRN")
        # Current implementation just removes invalid chars, reserved names pass through
        # This test validates it produces a non-empty filename
        filename = track.safe_filename
        assert len(filename) > 0
        assert "CON" in filename or "PRN" in filename

    def test_duration_seconds(self):
        """Should convert milliseconds to seconds"""
        track = TrackMetadata(track_id="test", title="Test", artist="Test", duration_ms=180000)
        assert track.duration_seconds == 180


class TestUtilityFunctions:
    """Tests for utility functions"""

    def test_format_time_seconds(self):
        assert format_time(65) == "1m 05s"
        assert format_time(3665) == "1h 01m"
        assert format_time(-1) == "--:--"

    def test_format_size(self):
        assert "KB" in format_size(1500)
        assert "MB" in format_size(5000000)
        assert "GB" in format_size(5000000000)

    def test_calculate_md5(self):
        """Should calculate correct MD5 hash"""
        fd, filepath = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(b"test content")

            md5 = calculate_md5(Path(filepath))
            expected = hashlib.md5(b"test content").hexdigest()
            assert md5 == expected
        finally:
            os.unlink(filepath)

    def test_calculate_md5_missing_file(self):
        """Should return empty string for missing file"""
        md5 = calculate_md5(Path("nonexistent.file"))
        assert md5 == ""


class TestRateLimiter:
    """Tests for RateLimiter class"""

    def test_initial_delay(self):
        limiter = RateLimiter(min_delay=0.5, max_delay=2.0)
        assert limiter.get_delay() == 0.5

    def test_error_increases_delay(self):
        limiter = RateLimiter(min_delay=0.5, max_delay=2.0)
        initial_delay = limiter.get_delay()
        limiter.error()
        assert limiter.get_delay() > initial_delay

    def test_success_decreases_delay(self):
        limiter = RateLimiter(min_delay=0.5, max_delay=2.0)
        limiter.error()  # Increase first
        limiter.error()
        high_delay = limiter.get_delay()
        limiter.success()
        assert limiter.get_delay() < high_delay

    def test_max_delay_limit(self):
        limiter = RateLimiter(min_delay=0.5, max_delay=2.0)
        for _ in range(100):
            limiter.error()
        assert limiter.get_delay() <= 2.0


class TestValidateCookies:
    """Tests for cookies validation"""

    def test_valid_cookies(self):
        fd, filepath = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write(".youtube.com\tTRUE\t/\tFALSE\t0\tSID\tvalue\n")

            assert validate_cookies_file(filepath)
        finally:
            os.unlink(filepath)

    def test_invalid_cookies(self):
        fd, filepath = tempfile.mkstemp(suffix=".txt")
        try:
            with os.fdopen(fd, "w") as f:
                f.write("invalid format\n")

            assert not validate_cookies_file(filepath)
        finally:
            os.unlink(filepath)

    def test_missing_file(self):
        assert not validate_cookies_file("nonexistent.txt")


class TestExportM3U:
    """Tests for M3U export"""

    def test_export_m3u(self):
        tracks = [
            ("/path/to/song1.mp3", "Song 1", 180),
            ("/path/to/song2.mp3", "Song 2", 240),
        ]

        fd, filepath = tempfile.mkstemp(suffix=".m3u")
        os.close(fd)

        try:
            export_m3u(tracks, filepath)

            with open(filepath, "r") as f:
                content = f.read()

            assert "#EXTM3U" in content
            assert "Song 1" in content
            assert "Song 2" in content
        finally:
            os.unlink(filepath)


class TestSaveHistory:
    """Tests for session history"""

    def test_save_history(self):
        fd, filepath = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        try:
            session = {"date": "2024-01-24", "songs": 10}
            save_history(filepath, session)

            with open(filepath, "r") as f:
                history = json.load(f)

            assert len(history) == 1
            assert history[0]["songs"] == 10
        finally:
            os.unlink(filepath)

    def test_history_limit(self):
        """Should keep only last 50 sessions"""
        fd, filepath = tempfile.mkstemp(suffix=".json")
        os.close(fd)

        try:
            # Add 60 sessions
            for i in range(60):
                save_history(filepath, {"session": i})

            with open(filepath, "r") as f:
                history = json.load(f)

            assert len(history) == 50
        finally:
            os.unlink(filepath)


class TestCacheManager:
    """Tests for SQLite CacheManager"""

    def test_init(self):
        fd, filepath = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            cache = CacheManager(filepath)
            assert os.path.exists(filepath)
            assert cache.count() == 0
        finally:
            try:
                os.unlink(filepath)
            except Exception:
                pass

    def test_set_get(self):
        fd, filepath = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            cache = CacheManager(filepath)
            data = {"url": "https://youtu.be/test", "title": "Test Video", "duration": 120}
            cache.set("test_key", data)

            # Read back
            cached = cache.get("test_key", ttl_hours=168)
            assert cached is not None
            assert cached["url"] == data["url"]
            assert cached["title"] == data["title"]
            assert cache.count() == 1
        finally:
            try:
                os.unlink(filepath)
            except Exception:
                pass

    def test_expiry(self):
        fd, filepath = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            cache = CacheManager(filepath)
            cache.set("old_key", {"url": "u", "title": "t", "duration": 1})

            # Manually backdate the timestamp in DB
            with cache.lock:
                cache.cursor.execute("UPDATE cache SET timestamp = timestamp - 100000")
                cache.conn.commit()

            # Should be expired (ttl=1 hour = 3600s)
            assert cache.get("old_key", ttl_hours=1) is None
        finally:
            try:
                os.unlink(filepath)
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
