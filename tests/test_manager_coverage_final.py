import asyncio
from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.core.manager import DownloadManager


@pytest.mark.asyncio
async def test_worker_exception_handling():
    """Test worker handles unexpected exceptions gracefully"""
    # Mock config to avoid real file paths
    cfg = MagicMock()
    cfg.DEBUG_MODE = True
    cfg.PROXIES_FILE = "p.txt"
    cfg.USE_PROXIES = False
    cfg.MAX_RETRIES = 1
    cfg.MAX_WORKERS = 1

    # Patch ProgressDB and CacheManager to avoid real DB init
    with (
        patch("resonance_audio_builder.core.manager.ProgressDB"),
        patch("resonance_audio_builder.core.manager.CacheManager"),
        patch("resonance_audio_builder.core.manager.RichUI"),
        patch("resonance_audio_builder.core.manager.SmartProxyManager"),
        patch("resonance_audio_builder.core.manager.KeyboardController") as mock_kb_cls,
    ):

        mock_kb = mock_kb_cls.return_value
        mock_kb.should_quit.return_value = False
        mock_kb.is_paused.return_value = False
        mock_kb.should_skip.return_value = False

        mgr = DownloadManager(cfg, MagicMock())
        # Re-assign mock_kb just in case init did something weird
        mgr.keyboard = mock_kb

        # Mock queue
        mgr.queue = asyncio.Queue()
        track = MagicMock()
        track.artist = "A"
        track.title = "T"
        track.track_id = "123"
        await mgr.queue.put(track)

        # Mock ui.add_download_task to raise an exception to hit the worker's outer catch block
        # Instead of _process_track_attempts which catches its own errors
        mgr.ui.add_download_task = MagicMock(side_effect=Exception("UI Critical Fail"))

        # Mock logger to verify error logged
        mgr.log = MagicMock()

        # Run worker task
        worker_task = asyncio.create_task(mgr._worker())

        # Give it enough time and ensure queue is processed
        # Wait up to 1 second for the task to finish (it won't, but let's check queue)
        for _ in range(10):
            if mgr.queue.empty():
                break
            await asyncio.sleep(0.1)

        # Cancel if still running
        if not worker_task.done():
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

        # Verify exception caught and logged
        # If _worker hits `except Exception`, it logs "Worker loop error: ..."
        mgr.log.error.assert_called()
