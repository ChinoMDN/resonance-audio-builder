import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from resonance_audio_builder.core.manager import DownloadManager
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult

class TestDownloadPipeline:
    """Tests end-to-end of the pipeline mock"""

    @pytest.fixture
    def manager(self, mock_youtube_api, tmp_path):
        # Mock Config
        cfg = MagicMock()
        cfg.MAX_RETRIES = 1
        cfg.MODE = "HQ"
        cfg.PROXIES_FILE = "proxies.txt" # Helper
        cfg.USE_PROXIES = False
        cfg.CACHE_FILE = "cache.json"
        mock_youtube_api.extract_info.return_value = {"entries": []}
        mock_youtube_api.__enter__.return_value = mock_youtube_api
        
        # Patch dependencies instantiated in __init__
        with patch("resonance_audio_builder.audio.youtube.yt_dlp.YoutubeDL", return_value=mock_youtube_api), \
             patch("asyncio.get_running_loop") as mock_loop, \
             patch("resonance_audio_builder.core.manager.RichUI"), \
             patch("resonance_audio_builder.core.manager.ProgressDB"), \
             patch("resonance_audio_builder.core.manager.SmartProxyManager"), \
             patch("resonance_audio_builder.core.manager.AudioDownloader"), \
             patch("resonance_audio_builder.core.manager.YouTubeSearcher"), \
             patch("resonance_audio_builder.core.manager.MetadataWriter"), \
             patch("resonance_audio_builder.core.manager.KeyboardController"):
            
            mgr = DownloadManager(cfg, MagicMock())
            # Replace components with fresh mocks for assertion
            mgr.searcher = MagicMock() 
            mgr.searcher.search = AsyncMock() # The method is async
            
            mgr.downloader = MagicMock()
            mgr.downloader.download = AsyncMock()
            
            mgr.state = MagicMock()
            mgr.state.is_done.return_value = False
            
            mgr.ui = MagicMock()
            
            mgr.keyboard = MagicMock()
            mgr.keyboard.is_paused.return_value = False
            mgr.keyboard.should_quit.return_value = False
            mgr.keyboard.should_skip.return_value = False
            
            return mgr

    @pytest.mark.asyncio
    async def test_full_pipeline_single_track(self, manager):
        """Happy path: Search -> Download -> Mark Done"""
        # A single track in queue
        track = TrackMetadata("id1", "Title", "Artist")
        await manager.queue.put(track)
        
        # Setup mocks
        manager.searcher.search = AsyncMock(return_value=SearchResult("url", "Title", 100))
        manager.downloader.download.return_value.success = True
        manager.downloader.download.return_value.skipped = False
        manager.downloader.download.return_value.bytes = 5000
        
        # Patch sleep ONLY inside the worker to speed it up
        with patch("resonance_audio_builder.core.manager.asyncio.sleep", new_callable=AsyncMock):
            task = asyncio.create_task(manager._worker())
            # Wait for the item to be processed
            await asyncio.wait_for(manager.queue.join(), timeout=2.0)
            task.cancel()
            try: await task; 
            except asyncio.CancelledError: pass
        
        assert manager.downloader.download.called
        assert manager.state.mark.called
        assert manager.state.mark.call_args[0][1] == "ok"

    @pytest.mark.asyncio
    async def test_pipeline_retry_logic(self, manager):
        """Should retry on RecoverableError"""
        track = TrackMetadata("id2", "RetryMe", "Artist")
        await manager.queue.put(track)
        
        from resonance_audio_builder.core.exceptions import RecoverableError
        # Setup mocks
        manager.searcher.search = AsyncMock(side_effect=[RecoverableError("Fail 1"), SearchResult("url", "Title", 100)])
        manager.downloader.download.return_value.success = True
        manager.downloader.download.return_value.skipped = False
        manager.downloader.download.return_value.bytes = 5000
        manager.cfg.MAX_RETRIES = 2
        
        with patch("resonance_audio_builder.core.manager.asyncio.sleep", new_callable=AsyncMock):
            task = asyncio.create_task(manager._worker())
            await asyncio.wait_for(manager.queue.join(), timeout=2.0)
            task.cancel()
            try: await task
            except: pass
        
        assert manager.searcher.search.call_count == 2
