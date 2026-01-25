import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from resonance_audio_builder.audio.downloader import AudioDownloader, DownloadResult
from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult

class TestAudioDownloader:
    @pytest.fixture
    def config(self, tmp_path):
        cfg = Config()
        cfg.OUTPUT_FOLDER_HQ = str(tmp_path / "HQ")
        cfg.OUTPUT_FOLDER_MOBILE = str(tmp_path / "Mobile")
        return cfg

    @pytest.fixture
    def downloader(self, config):
        return AudioDownloader(config, MagicMock())

    @pytest.mark.asyncio
    async def test_download_success_hq_only(self, downloader):
        """Test basic successful download flow (HQ only)"""
        downloader.cfg.MODE = QualityMode.HQ_ONLY
        
        # Mock raw download
        with patch.object(downloader, "_download_raw", new_callable=AsyncMock) as mock_raw, \
             patch.object(downloader, "_transcode", new_callable=AsyncMock) as mock_transcode, \
             patch.object(downloader, "_inject_metadata", new_callable=AsyncMock):
             
             mock_raw.return_value = Path("raw_temp.webm")
             mock_transcode.return_value = True
             
             # Mock file existence checks on raw path
             with patch("pathlib.Path.exists", return_value=True), \
                  patch("pathlib.Path.stat") as mock_stat:
                  mock_stat.return_value.st_size = 5000
                  
                  res = await downloader.download(
                      SearchResult("vid", "Title", 100, "url"),
                      TrackMetadata("id1", "Title", "Artist")
                  )
                  
                  assert res.success is True
                  assert res.skipped is False

    @pytest.mark.asyncio
    async def test_download_skip_existing(self, downloader, tmp_path):
        """Should skip if file exists and validates"""
        downloader.cfg.MODE = QualityMode.HQ_ONLY
        hq_file = Path(downloader.cfg.OUTPUT_FOLDER_HQ) / "Artist - Title.mp3"
        hq_file.parent.mkdir(parents=True, exist_ok=True)
        hq_file.touch()
        
        with patch.object(downloader, "validate_audio_file", new_callable=AsyncMock) as mock_val:
            mock_val.return_value = True
            
            res = await downloader.download(
                SearchResult("vid", "Title", 100, "url"),
                TrackMetadata("id2", "Title", "Artist")
            )
            
            assert res.success is True
            assert res.skipped is True

    @pytest.mark.asyncio
    async def test_transcode_calls_ffmpeg(self, downloader):
        """Transcode should invoke ffmpeg subprocess"""
        input_p = Path("in.webm")
        output_p = Path("out.mp3")
        
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            process = AsyncMock()
            process.returncode = 0
            process.communicate.return_value = (b"", b"")
            mock_exec.return_value = process
            
            # Mock file check after transcode
            with patch("pathlib.Path.exists", side_effect=[True, True, True]), \
                 patch("pathlib.Path.stat") as mock_stat:
                 mock_stat.return_value.st_size = 1000
                 
                 success = await downloader._transcode(input_p, output_p, "320")
                 assert success is True
                 assert mock_exec.called
                 args = mock_exec.call_args[0]
                 assert "ffmpeg" in args
                 assert "320k" in args
