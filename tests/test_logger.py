import pytest
from unittest.mock import MagicMock
from resonance_audio_builder.core.logger import Logger

class TestLogger:
    def test_logger_info(self):
        ui = MagicMock()
        logger = Logger(debug=True)
        logger.set_tracker(ui)
        
        logger.info("Test Info")
        assert ui.add_log.called
        assert "Test Info" in ui.add_log.call_args[0][0]

    def test_logger_debug_disabled(self):
        ui = MagicMock()
        logger = Logger(debug=False)
        logger.set_tracker(ui)
        
        logger.debug("Test Debug")
        assert not ui.add_log.called

    def test_logger_error(self):
        ui = MagicMock()
        logger = Logger(debug=True)
        logger.set_tracker(ui)
        
        logger.error("Test Error")
        assert ui.add_log.called
        assert "[X]" in ui.add_log.call_args[0][0]
