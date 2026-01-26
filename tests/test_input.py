import pytest
import threading
from unittest.mock import MagicMock, patch
from resonance_audio_builder.core.input import KeyboardController
from resonance_audio_builder.core.logger import Logger

class TestKeyboardController:
    @pytest.fixture
    def controller(self):
        logger = MagicMock(spec=Logger)
        return KeyboardController(logger)

    def test_initial_state(self, controller):
        assert controller.is_paused() is False
        assert controller.should_quit() is False
        assert controller.should_skip() is False

    def test_handle_pause(self, controller):
        controller._handle_key("P")
        assert controller.is_paused() is True
        controller._handle_key("P")
        assert controller.is_paused() is False

    def test_handle_skip(self, controller):
        controller._handle_key("S")
        assert controller.should_skip() is True
        # Should clear after check
        assert controller.should_skip() is False

    def test_handle_quit(self, controller):
        controller._handle_key("Q")
        assert controller.should_quit() is True

    def test_start_stop(self, controller):
        with patch("threading.Thread") as mock_thread:
            controller.start()
            assert controller._running is True
            assert mock_thread.called
            
            controller.stop()
            assert controller._running is False
