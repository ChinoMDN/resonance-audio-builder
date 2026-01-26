import subprocess
from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.audio.downloader import AudioDownloader


class TestDownloaderCoverageFinal:
    @pytest.fixture
    def downloader(self):
        cfg = MagicMock()
        log = MagicMock()
        cache = MagicMock()
        return AudioDownloader(cfg, log, cache)

    @pytest.mark.asyncio
    async def test_download_with_quit_signal(self, downloader):
        """Test download respects quit signal"""
        # Mock search result and track
        search_result = MagicMock()
        track = MagicMock()

        def quit_flag():
            return True  # Simulate immediate quit

        result = await downloader.download(search_result, track, check_quit=quit_flag)

        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_transcode_timeout(self, downloader, tmp_path):
        """Test FFmpeg timeout handling"""
        input_file = tmp_path / "input.mp3"
        output_file = tmp_path / "output.mp3"

        with patch("pathlib.Path.exists", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 300)):
                result = await downloader._transcode(input_file, output_file, "320")
                assert result is False

    @pytest.mark.asyncio
    async def test_download_cover_network_error(self, downloader):
        """Test cover download with network failure"""
        with patch("aiohttp.ClientSession") as mock_session_cls:
            mock_session = mock_session_cls.return_value.__aenter__.return_value
            mock_session.get.side_effect = Exception("Network Error")

            result = await downloader._download_cover("http://example.com/cover.jpg")
            assert result is None
