"""Benchmarks for AudioDownloader components — cover resize, ytdlp options, cover embed."""

import io
from unittest.mock import MagicMock

import pytest
from PIL import Image

from resonance_audio_builder.audio.downloader import AudioDownloader
from resonance_audio_builder.core.config import Config


@pytest.fixture
def downloader():
    """Create a minimal AudioDownloader with mocked dependencies."""
    cfg = MagicMock(spec=Config)
    cfg.COOKIES_FILE = ""
    cfg.SPECTRAL_ANALYSIS = False
    cfg.SPECTRAL_CUTOFF = 16000
    cfg.DEBUG_MODE = False
    cfg.SEARCH_TIMEOUT = 30
    log = MagicMock()
    return AudioDownloader(cfg, log, None)


def _make_jpeg(width: int = 640, height: int = 640) -> bytes:
    """Generate a minimal JPEG image in memory."""
    img = Image.new("RGB", (width, height), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _make_png(width: int = 640, height: int = 640) -> bytes:
    """Generate a minimal PNG image in memory."""
    img = Image.new("RGBA", (width, height), color=(73, 109, 137, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestCoverResizeBenchmarks:
    """Benchmarks for cover image resizing pipeline."""

    def test_resize_small_jpeg_no_op(self, benchmark, downloader):
        """Benchmark: Small image (300x300) — should skip resize."""
        data = _make_jpeg(300, 300)
        benchmark(downloader._resize_cover_sync, data, 600)

    def test_resize_large_jpeg(self, benchmark, downloader):
        """Benchmark: Large image (1200x1200) — triggers resize to 600x600."""
        data = _make_jpeg(1200, 1200)
        benchmark(downloader._resize_cover_sync, data, 600)

    def test_resize_hd_jpeg(self, benchmark, downloader):
        """Benchmark: HD image (2400x2400) — heavy resize."""
        data = _make_jpeg(2400, 2400)
        benchmark(downloader._resize_cover_sync, data, 600)

    def test_resize_png_to_jpeg_conversion(self, benchmark, downloader):
        """Benchmark: PNG to JPEG conversion during resize."""
        data = _make_png(1200, 1200)
        benchmark(downloader._resize_cover_sync, data, 600)


class TestCoverEmbedBenchmarks:
    """Benchmarks for cover art format detection and embedding logic."""

    def test_embed_cover_jpeg_detection(self, benchmark, downloader):
        """Benchmark: JPEG magic byte detection + MP4Cover creation."""
        jpeg_data = _make_jpeg(600, 600)
        audio = MagicMock()

        def embed():
            downloader._embed_cover_m4a(audio, jpeg_data)

        benchmark(embed)

    def test_embed_cover_png_detection(self, benchmark, downloader):
        """Benchmark: PNG magic byte detection + MP4Cover creation."""
        png_data = _make_png(600, 600)
        audio = MagicMock()

        def embed():
            downloader._embed_cover_m4a(audio, png_data)

        benchmark(embed)


class TestYtdlpOptionsBenchmarks:
    """Benchmarks for yt-dlp configuration dictionary construction."""

    def test_build_ytdlp_options_no_proxy(self, benchmark, downloader):
        """Benchmark: Build yt-dlp options without proxy."""
        from pathlib import Path

        benchmark(downloader._get_ytdlp_options, Path("/tmp/out.%(ext)s"), None)

    def test_build_ytdlp_options_with_proxy(self, benchmark, downloader):
        """Benchmark: Build yt-dlp options with proxy."""
        from pathlib import Path

        benchmark(
            downloader._get_ytdlp_options,
            Path("/tmp/out.%(ext)s"),
            "http://proxy:8080",
        )
