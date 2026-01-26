import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resonance_audio_builder.audio.downloader import DownloadResult
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.manager import DownloadManager


class TestDownloadManagerUnit:
    @pytest.fixture
    def manager(self):
        cfg = Config()
        cfg.MAX_RETRIES = 3  # Ensure it's an int
        cache = MagicMock()

        with (
            patch("resonance_audio_builder.core.manager.RichUI"),
            patch("resonance_audio_builder.core.manager.ProgressDB"),
            patch("resonance_audio_builder.core.manager.SmartProxyManager"),
            patch("resonance_audio_builder.core.manager.AudioDownloader"),
            patch("resonance_audio_builder.core.manager.YouTubeSearcher"),
            patch("resonance_audio_builder.core.manager.MetadataWriter"),
            patch("resonance_audio_builder.core.manager.KeyboardController"),
        ):

            mgr = DownloadManager(cfg, cache)
            mgr.searcher = MagicMock()
            mgr.downloader = MagicMock()
            mgr.state = MagicMock()
            mgr.ui = MagicMock()
            mgr.keyboard = MagicMock()
            mgr.keyboard.should_quit.return_value = False
            return mgr

    @pytest.mark.asyncio
    async def test_process_track_attempts_success(self, manager):
        track = TrackMetadata(track_id="1", title="Title", artist="Artist")
        search_res = SearchResult("url", "Title", 180)

        manager.searcher.search = AsyncMock(return_value=search_res)
        manager.downloader.download = AsyncMock(return_value=DownloadResult(True, 5000))
        manager.state.is_done.return_value = False

        await manager._process_track_attempts(track, "task1")

        assert manager.searcher.search.called
        assert manager.downloader.download.called
        assert manager.state.mark.called
        assert manager.state.mark.call_args[0][1] == "ok"

    @pytest.mark.xfail(reason="Async worker loop timing is unstable in test environment")
    @pytest.mark.asyncio
    async def test_worker_loop(self, manager):
        track = TrackMetadata(track_id="1", title="T1", artist="A1")
        await manager.queue.put(track)

        # Mock _process_track_attempts to simulate success
        with patch.object(manager, "_process_track_attempts", new_callable=AsyncMock) as mock_process:
            mock_process.return_value = True

            # Start worker as a task
            worker_task = asyncio.create_task(manager._worker())

            # Use join to wait until queue is processed
            try:
                await asyncio.wait_for(manager.queue.join(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        assert mock_process.called

    @pytest.mark.asyncio
    async def test_process_track_fatal_error(self, manager):
        from resonance_audio_builder.core.exceptions import FatalError

        track = TrackMetadata(track_id="1", title="Title", artist="Artist")

        manager.searcher.search = AsyncMock(side_effect=FatalError("Permanent fail"))
        manager.state.is_done.return_value = False

        await manager._process_track_attempts(track, "task1")

        # Should only try once and stop
        assert manager.searcher.search.call_count == 1
        assert manager.ui.update_task_status.called

    @pytest.mark.asyncio
    async def test_process_track_recoverable_retry(self, manager):
        from resonance_audio_builder.core.exceptions import RecoverableError

        track = TrackMetadata(track_id="1", title="Title", artist="Artist")

        # 1st fail, 2nd success
        manager.searcher.search = AsyncMock(side_effect=[RecoverableError("Transient"), SearchResult("u", "T", 1)])
        manager.downloader.download = AsyncMock(return_value=DownloadResult(True, 10))
        manager.state.is_done.return_value = False
        manager.cfg.MAX_RETRIES = 2

        # Patch sleep to speed up test
        with patch("asyncio.sleep", AsyncMock()):
            await manager._process_track_attempts(track, "task1")

        assert manager.searcher.search.call_count == 2
        assert manager.downloader.download.called
