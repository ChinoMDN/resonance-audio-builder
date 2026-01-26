import pytest
import time
import threading
from unittest.mock import MagicMock, patch, AsyncMock
from resonance_audio_builder.network.limiter import RateLimiter, CircuitBreaker
from resonance_audio_builder.audio.tagging import MetadataWriter
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.network.cache import CacheManager
from pathlib import Path

class TestCoverageBooster:
    def test_limiter_wait_logic(self):
        """Force rate limiter to actually wait (Sync)"""
        limiter = RateLimiter(min_delay=1.0, max_delay=5.0)
        limiter.current_delay = 2.0
        
        with patch("time.sleep") as mock_sleep:
            limiter.wait()
            mock_sleep.assert_called()

    def test_limiter_error_backoff_max(self):
        """Test max backoff"""
        limiter = RateLimiter(min_delay=1.0, max_delay=2.0)
        limiter.error() # increases delay
        limiter.error() 
        for _ in range(5):
             limiter.error()
        # With max_delay 2.0, it should be around 2.0
        assert limiter.current_delay <= 2.2 # Allow for jitter

    def test_circuit_breaker(self):
        """Test CircuitBreaker logic"""
        cb = CircuitBreaker(threshold=2, cooldown=100)
        cb.record_failure()
        assert cb.state == "CLOSED"
        cb.record_failure() # 2nd failure
        assert cb.state == "OPEN"
        
        # Check raises
        with pytest.raises(Exception) as exc:
            cb.check()
        assert "Circuit Breaker OPEN" in str(exc.value)
        
        # Test cooldown expiry (simulate time passing)
        with patch("time.time", side_effect=[1000, 2000]):
             # 1000 set as last_failure (mocked?) no, record_failure calls time.time()
             # We need to control time inside record_failure and check
             pass
             
        # Easier: Manually set vars
        cb.state = "OPEN"
        cb.last_failure_time = time.time() - 200 # elapsed=200 > cooldown=100
        cb.check() 
        assert cb.state == "HALF_OPEN"
        
        # Record success closes it
        cb.record_success()
        assert cb.state == "CLOSED"

    def test_tagging_write_full(self, tmp_path):
        """Test complete tagging flow"""
        from resonance_audio_builder.audio.tagging import MetadataWriter
        from resonance_audio_builder.audio.metadata import TrackMetadata
        from unittest.mock import Mock
        
        # Create REAL tiny MP3 file instead of mock
        audio_file = tmp_path / "test.mp3"
        
        # Create a minimal valid MP3 header
        # MP3 frame sync: 0xFF 0xFB (MPEG-1 Layer 3)
        mp3_header = bytes([
            0xFF, 0xFB,  # Sync + MPEG-1 Layer 3
            0x90, 0x00,  # Bitrate + sample rate
        ] + [0x00] * 100)  # Padding
        
        audio_file.write_bytes(mp3_header)
        
        track = TrackMetadata(
            track_id="id_123",
            title="Test", 
            artist="Artist",
            raw_data={}
        )
        
        # Mock Logger
        mock_log = Mock()
        
        # Mock MP3 to avoid real file parsing issues
        with patch("resonance_audio_builder.audio.tagging.MP3") as mock_mp3_cls:
            mock_audio = MagicMock()
            mock_mp3_cls.return_value = mock_audio
            # mocked audio tags shouldn't be None for add_tags skip? 
            # code: if audio.tags is None: audio.add_tags()
            mock_audio.tags = MagicMock() 
            
            writer = MetadataWriter(mock_log)
            writer.write(audio_file, track)
            
            # Should have called save
            mock_audio.save.assert_called()
            
            # Should NOT have logged error
            mock_log.error.assert_not_called()

    def test_cache_exception_branches(self):
        """Cover CacheManager exception blocks"""
        # Force exceptions by passing invalid path that might fail connect or mocking
        with patch("sqlite3.connect", side_effect=Exception("DB Fail")):
             # __init__ catches exception
             cm = CacheManager("bad.db") # Prints error
             assert not hasattr(cm, "cursor")
             # methods should return safe defaults
             assert cm.get("k", 1) is None
             cm.set("k", {"url": "u", "title": "t"}) 
             assert cm.count() == 0
             
        # Test clear lock acquire fail (timeout)
        with patch("sqlite3.connect"):
            cm = CacheManager("ok.db")
            # Replace lock with mock that fails acquire
            cm.lock = MagicMock()
            cm.lock.acquire.return_value = False
            
            cm.clear() # Should return early
            cm.lock.acquire.assert_called()
