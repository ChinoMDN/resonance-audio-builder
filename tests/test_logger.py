from unittest.mock import MagicMock

from resonance_audio_builder.core.logger import Logger


class TestLogger:
    def test_logger_info(self):
        ui = MagicMock()
        log = Logger(debug=True)
        log.set_tracker(ui)
        log.info("Test Info")

        # Check interaction with UI
        assert ui.add_log.called
        args, _ = ui.add_log.call_args
        assert "Test Info" in args[0]

    def test_logger_debug_disabled(self):
        ui = MagicMock()
        log = Logger(debug=False)
        log.set_tracker(ui)
        log.debug("Hidden")
        assert not ui.add_log.called

    def test_logger_error(self):
        ui = MagicMock()
        log = Logger(debug=True)
        log.set_tracker(ui)
        log.error("Boom")
        assert ui.add_log.called
