import pytest
import subprocess
import requests
from unittest.mock import MagicMock, patch
from pathlib import Path
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
        
        quit_flag = lambda: True  # Simulate immediate quit
        
        result = await downloader.download(
            search_result, 
            track, 
            check_quit=quit_flag
        )
        
        assert result.skipped is True

    @pytest.mark.asyncio
    async def test_transcode_timeout(self, downloader, tmp_path):
        """Test FFmpeg timeout handling"""
        input_file = tmp_path / "input.mp3"
        output_file = tmp_path / "output.mp3"
        input_file.touch()
        
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("ffmpeg", 300)):
            result = await downloader._transcode(input_file, output_file, "320")
            assert result is False

    @pytest.mark.asyncio
    async def test_download_cover_network_error(self, downloader):
        """Test cover download with network failure"""
        with patch('resonance_audio_builder.audio.downloader.aiohttp.ClientSession') as mock_session:
             # Just ensure it handles exceptions if it uses aiohttp or requests?
             # Coverage report says lines 258-271 missing which is _download_cover.
             # Code uses requests or aiohttp?
             # Actually code might use requests.get in some versions or aiohttp.
             # User snippet used requests.get in previous turn.
             # Let's check error: "coroutine object ... is None". So it IS async.
             # If it is async, it likely uses aiohttp.
             # If I await it, I need to patch aiohttp or whatever it uses.
             # But if it catches generic Exception, side_effect on expected call works.
             # Let's try awaiting it first.
             pass
             
        with patch('aiohttp.ClientSession') as mock_session_cls:
            mock_session = mock_session_cls.return_value.__aenter__.return_value
            mock_session.get.side_effect = Exception("Network Error")
            
            result = await downloader._download_cover("http://example.com/cover.jpg")
            assert result is None
