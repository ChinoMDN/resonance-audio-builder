from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from resonance_audio_builder.core.builder import App
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.audio.metadata import TrackMetadata


class TestBuilderMenuAndAudit:
    @pytest.fixture
    def app(self, tmp_path):
        with patch("resonance_audio_builder.core.builder.Config.load") as mock_load:
            cfg = Config()
            cfg.INPUT_FOLDER = str(tmp_path / "Playlists")
            cfg.OUTPUT_FOLDER_HQ = str(tmp_path / "HQ")
            cfg.OUTPUT_FOLDER_MOBILE = str(tmp_path / "Mobile")
            cfg.CHECKPOINT_FILE = str(tmp_path / "progress.json")
            mock_load.return_value = cfg

            with (
                patch("resonance_audio_builder.core.builder.ProgressDB"),
                patch("resonance_audio_builder.core.builder.CacheManager"),
                patch("resonance_audio_builder.core.builder.Logger"),
            ):
                return App()

    def test_run_audit_no_results(self, app):
        auditor = MagicMock()
        auditor.scan_library.return_value = {}

        with (
            patch("resonance_audio_builder.core.builder.AudioAuditor",
                  return_value=auditor),
            patch("resonance_audio_builder.core.builder.Prompt.ask",
                  return_value="n"),
            patch("resonance_audio_builder.core.builder.console.print") as mock_print,
            patch("resonance_audio_builder.core.builder.console.input"),
            patch("resonance_audio_builder.core.builder.print_header"),
        ):
            app._run_audit()
            assert mock_print.called

    def test_run_audit_with_results_and_spectral(self, app):
        result = SimpleNamespace(
            total_files=10,
            total_size_bytes=4096,
            missing_metadata=["a.mp3"],
            missing_covers=["b.mp3"],
            missing_lyrics=["c.mp3"],
            fake_hq_detected=["hq_fake.mp3"],
            errors=["broken file"],
        )
        auditor = MagicMock()
        auditor.scan_library.return_value = {"HQ": result}

        with (
            patch("resonance_audio_builder.core.builder.AudioAuditor",
                  return_value=auditor),
            patch("resonance_audio_builder.core.builder.Prompt.ask",
                  return_value="y"),
                patch("resonance_audio_builder.core.builder.console.expander",
                      return_value=nullcontext(), create=True),
            patch("resonance_audio_builder.core.builder.console.print") as mock_print,
            patch("resonance_audio_builder.core.builder.console.input"),
            patch("resonance_audio_builder.core.builder.print_header"),
        ):
            app._run_audit()
            assert mock_print.called

    def test_start_download_writes_crash_log_on_critical_error(self, app, tmp_path):
        fake_track = TrackMetadata(
            track_id="id-1", title="Song", artist="Artist")

        with (
            patch.object(app, "_get_selected_csvs",
                         return_value=["ignored.csv"]),
            patch.object(app, "_select_quality"),
            patch.object(app, "_collect_tracks", return_value=[fake_track]),
            patch("resonance_audio_builder.core.builder.DownloadManager",
                  side_effect=RuntimeError("boom")),
            patch("resonance_audio_builder.core.builder.traceback.format_exc",
                  return_value="trace"),
            patch("resonance_audio_builder.core.builder.open", mock_open(), create=True) as mocked_open,
            patch("resonance_audio_builder.core.builder.console.print"),
            patch("resonance_audio_builder.core.builder.console.input"),
        ):
            app._start_download()
            mocked_open.assert_called_once_with(
                "crash.log", "w", encoding="utf-8")

    def test_run_routes_to_exit_option(self, app):
        with (
            patch.object(app, "_check_dependencies", return_value=True),
            patch.object(app, "_show_status"),
            patch("resonance_audio_builder.core.builder.Prompt.ask",
                  side_effect=["5"]),
            patch("resonance_audio_builder.core.builder.console.print") as mock_print,
            patch("resonance_audio_builder.core.builder.print_header"),
        ):
            app.run()
            assert mock_print.called

    def test_run_routes_to_download_and_notify(self, app):
        with (
            patch.object(app, "_check_dependencies", return_value=True),
            patch.object(app, "_show_status"),
            patch.object(app, "_start_download") as mock_start_download,
            patch.object(app, "_notify_end") as mock_notify,
            patch("resonance_audio_builder.core.builder.Prompt.ask",
                  side_effect=["1", "5"]),
            patch("resonance_audio_builder.core.builder.console.input"),
            patch("resonance_audio_builder.core.builder.console.print"),
            patch("resonance_audio_builder.core.builder.print_header"),
        ):
            app.run()
            assert mock_start_download.called
            assert mock_notify.called
