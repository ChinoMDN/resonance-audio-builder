from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.core.ui import RichUI, format_time, print_header


class TestRichUI:
    @pytest.fixture
    def ui(self):
        cfg = MagicMock()
        return RichUI(cfg)

    def test_start_stop(self, ui):
        with patch("resonance_audio_builder.core.ui.Live") as mock_live:
            ui.start(10)
            assert ui.live is not None
            assert mock_live.called

            mock_instance = ui.live
            ui.stop()
            # stop() calls self.live.stop()
            assert mock_instance.stop.called

    def test_add_download_task(self, ui):
        ui.start(1)
        # Mocking progress objects
        ui.job_progress = MagicMock()
        ui.job_progress.add_task.return_value = "id123"

        tid = ui.add_download_task("Artist", "Title")
        assert tid == "id123"
        assert ui.active_tasks["id123"].artist == "Artist"

    def test_update_task_status(self, ui):
        ui.job_progress = MagicMock()
        ui.job_progress._tasks = {"id1": MagicMock()}

        ui.update_task_status("id1", "Downloading")
        ui.job_progress.update.assert_called_with("id1", status="Downloading")

    def test_update_main_progress(self, ui):
        ui.overall_progress = MagicMock()
        ui.main_task = "main"

        ui.update_main_progress(1)
        ui.overall_progress.update.assert_called_with("main", advance=1)

    def test_format_time_edge_cases(self):
        """Test time formatting edge cases"""
        assert format_time(0) == "0m 00s"
        assert format_time(60) == "1m 00s"
        assert format_time(3661) == "1h 01m"

    def test_print_header(self):
        """Test header printing"""
        with patch("resonance_audio_builder.core.ui.console.print") as mock_print:
            print_header()
            assert mock_print.called

    def test_show_summary(self, ui):
        """Test summary display"""
        with patch("resonance_audio_builder.core.ui.console.print") as mock_print:
            ui.show_summary({"ok": 1, "skip": 0, "error": 0, "bytes": 100})
            assert mock_print.called
