import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from resonance_audio_builder.core.manager import DownloadManager
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.exceptions import FatalError
from resonance_audio_builder.audio.metadata import TrackMetadata

@pytest.fixture
def manager():
    cfg = Config()
    cache = MagicMock()
    with (
        patch("resonance_audio_builder.core.manager.RichUI"),
        patch("resonance_audio_builder.core.manager.ProgressDB"),
        patch("resonance_audio_builder.core.manager.SmartProxyManager"),
        patch("resonance_audio_builder.core.manager.AudioDownloader"),
        patch("resonance_audio_builder.core.manager.YouTubeSearcher"),
        patch("resonance_audio_builder.core.manager.MetadataWriter"),
        patch("resonance_audio_builder.core.manager.KeyboardController"),
        patch("resonance_audio_builder.network.limiter.CircuitBreaker") as MockCB
    ):
        mgr = DownloadManager(cfg, cache)
        # Verify CB was init
        assert mgr.circuit_breaker is not None
        mgr.ui = MagicMock()
        mgr.state = MagicMock()
        mgr.state.is_done.return_value = False
        mgr.keyboard = MagicMock()
        mgr.keyboard.should_quit.return_value = False
        return mgr

@pytest.mark.asyncio
async def test_circuit_breaker_record_failure_on_429(manager):
    track = TrackMetadata(track_id="1", title="T", artist="A")
    # Simulate FatalError with 429
    manager.searcher.search = AsyncMock(side_effect=FatalError("HTTP 429 Too Many Requests"))
    
    await manager._process_track_attempts(track, "task1")
    
    manager.circuit_breaker.record_failure.assert_called_once()

@pytest.mark.asyncio
async def test_circuit_breaker_record_failure_on_403(manager):
    track = TrackMetadata(track_id="1", title="T", artist="A")
    # Simulate FatalError with 403
    manager.searcher.search = AsyncMock(side_effect=FatalError("HTTP 403 Forbidden"))
    
    await manager._process_track_attempts(track, "task1")
    
    manager.circuit_breaker.record_failure.assert_called_once()

@pytest.mark.asyncio
async def test_circuit_breaker_no_record_on_generic_fatal(manager):
    track = TrackMetadata(track_id="1", title="T", artist="A")
    # Generic fatal error (e.g. ffmpeg missing)
    manager.searcher.search = AsyncMock(side_effect=FatalError("FFmpeg not found"))
    
    await manager._process_track_attempts(track, "task1")
    
    # Should NOT record failure for circuit breaker (it's not a rate limit issue)
    manager.circuit_breaker.record_failure.assert_not_called()

@pytest.mark.asyncio
async def test_circuit_breaker_record_success(manager):
    track = TrackMetadata(track_id="1", title="T", artist="A")
    
    # Simulate success
    manager.searcher.search = AsyncMock(return_value="result")
    manager.downloader.download = AsyncMock(return_value=MagicMock(success=True, skipped=False, bytes=100))
    
    await manager._process_track_attempts(track, "task1")
    
    manager.circuit_breaker.record_success.assert_called_once()


