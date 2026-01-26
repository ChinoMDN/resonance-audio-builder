from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.core.ui import format_time, print_header


class TestUICoverage:
    def test_format_time_edge_cases(self):
        """Test time formatting edge cases"""
        assert format_time(0) == "0m 00s"
        assert format_time(59) == "0m 59s"
        assert format_time(60) == "1m 00s"
        assert format_time(3661) == "1h 01m"

    def test_print_header(self):
        """Test header printing"""
        with patch("resonance_audio_builder.core.ui.console.print") as mock_print:
            print_header()
            assert mock_print.called


class TestInputCoverage:
    def test_handle_keys(self):
        """Test KeyboardController key handling"""
        from resonance_audio_builder.core.input import KeyboardController

        kb = KeyboardController(MagicMock())

        # Test Pause toggle
        kb._handle_key("P")
        assert kb.is_paused()
        kb._handle_key("P")
        assert not kb.is_paused()

        # Test Skip
        kb._handle_key("S")
        assert kb.should_skip()
        assert not kb.should_skip()  # clears after check

        # Test Quit
        kb._handle_key("Q")
        assert kb.should_quit()


class TestRichUICoverageBoost:
    def test_ui_methods(self):
        """Test various RichUI methods"""
        from resonance_audio_builder.core.ui import RichUI

        cfg = MagicMock()
        ui = RichUI(cfg)

        # Patch the class itself to avoid global state issues
        with patch("resonance_audio_builder.core.ui.Live") as mock_live_cls:
            mock_live = mock_live_cls.return_value
            ui.start(10)
            ui.add_log("Test Log")
            ui.update_main_progress(1)
            tid = ui.add_download_task("Artist", "Title")
            ui.update_task_status(tid, "Done")
            ui.remove_task(tid)
            ui.stop()
            assert mock_live.start.called
            assert mock_live.stop.called

        # Test summary
        with patch("resonance_audio_builder.core.ui.console.print") as mock_print:
            ui.show_summary({"ok": 1, "skip": 0, "error": 0, "bytes": 100})
            assert mock_print.called


class TestDownloaderCoverageDeep:
    @pytest.fixture
    def downloader(self):
        from resonance_audio_builder.audio.downloader import AudioDownloader

        cfg = MagicMock()
        log = MagicMock()
        # Fix: 3rd arg is proxy_manager, not cache
        return AudioDownloader(cfg, log, None)

    @pytest.mark.asyncio
    async def test_download_cover_success(self, downloader):
        """Test successful cover download with actual fake data"""
        from unittest.mock import AsyncMock

        # Mock aiohttp response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read = AsyncMock(return_value=b"fake_image_data")
        # Ensure __aenter__ returns the response
        mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_resp.__aexit__ = AsyncMock()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        # Ensure session __aenter__ returns the session
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("aiohttp.ClientSession", return_value=mock_session):
            img = await downloader._download_cover("http://example.com/art.jpg")
            assert img == b"fake_image_data"
