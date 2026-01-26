import threading
from unittest.mock import patch
import time

from resonance_audio_builder.network.limiter import RateLimiter


class TestRateLimiter:
    def test_initial_delay(self):
        """Initial delay should be min_delay"""
        rl = RateLimiter(min_delay=1.0, max_delay=5.0)
        assert rl.current_delay == 1.0

    @patch("time.sleep")
    def test_wait(self, mock_sleep):
        """Wait calls sleep with current delay + jitter"""
        rl = RateLimiter(min_delay=1.0)
        rl.wait()
        assert mock_sleep.called
        # Check that it slept for at least min_delay (jitter is 0 to 0.5)
        args, _ = mock_sleep.call_args
        assert args[0] >= 1.0

    def test_success_reduces_delay(self):
        """Success reduces delay"""
        rl = RateLimiter(min_delay=1.0)
        rl.current_delay = 5.0
        rl.success()
        assert rl.current_delay < 5.0

    def test_error_increases_delay(self):
        """Error increases delay exponentially"""
        rl = RateLimiter(min_delay=1.0)
        rl.error()
        assert rl.current_delay > 1.0

        prev = rl.current_delay
        rl.error()
        assert rl.current_delay > prev

    def test_max_delay_cap(self):
        """Delay should not exceed max"""
        rl = RateLimiter(max_delay=10.0)
        rl.current_delay = 9.0
        rl.error()  # 9 * 1.5 = 13.5 > 10
        assert rl.current_delay == 10.0

    def test_concurrent_usage(self):
        """Thread safety check"""
        rl = RateLimiter()

        def worker():
            for _ in range(100):
                rl.success()
                rl.error()

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Just checking no crash + value is float
        assert isinstance(rl.current_delay, float)
