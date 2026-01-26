import sys
from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.core.builder import App
from resonance_audio_builder.core.config import QualityMode


class TestAppExpanded:
    @pytest.fixture
    def app(self):
        with (
            patch("resonance_audio_builder.core.builder.Config.load") as mock_load,
            patch("resonance_audio_builder.core.builder.CacheManager") as mock_cache_cls,
            patch("resonance_audio_builder.core.builder.ProgressDB"),
        ):

            mock_load.return_value = MagicMock()
            mock_load.return_value.DEBUG_MODE = False
            mock_load.return_value.RATE_LIMIT_MIN = 0.5
            mock_load.return_value.RATE_LIMIT_MAX = 2.0
            mock_load.return_value.INPUT_FOLDER = "Playlists"
            mock_load.return_value.COOKIES_FILE = "cookies.txt"
            mock_load.return_value.MODE = QualityMode.BOTH

            mock_cache_cls.return_value = MagicMock()

            app = App()
            # Mock internal components to isolate test (though already mocked by class patch)
            app.db = MagicMock()
            # app.cache is already the return value of mock_cache_cls
            app.log = MagicMock()
            return app

    def test_show_status(self, app):
        with (
            patch("resonance_audio_builder.core.builder.console.print") as mock_print,
            patch("resonance_audio_builder.core.builder.validate_cookies_file", return_value=True),
            patch("shutil.which", return_value=True),
        ):

            app.db.get_stats.return_value = {"ok": 10, "skip": 5, "error": 2}
            app.cache.count.return_value = 100

            app._show_status()

            assert mock_print.called

    def test_collect_tracks(self, app, tmp_path):
        # Create dummy CSVs
        header = (
            "Track URI,Track Name,Artist Name,Album Name,Disc Number,"
            "Track Number,Track Duration (ms),Added By,Added At,ISRC\n"
        )
        csv1 = tmp_path / "list1.csv"
        csv1.write_text(
            f"{header}spotify:track:123,Song1,Artist1,Album1,1,1,1000,User,Date,ISRC1",
            encoding="utf-8",
        )

        csv2 = tmp_path / "list2.csv"
        csv2.write_text(
            f"{header}spotify:track:456,Song2,Artist2,Album2,1,1,2000,User,Date,ISRC2",
            encoding="utf-8",
        )

        tracks = app._collect_tracks([str(csv1), str(csv2)])
        assert len(tracks) == 2
        assert tracks[0].playlist_subfolder == "list1"
        assert tracks[1].playlist_subfolder == "list2"

    @patch("resonance_audio_builder.core.builder.DownloadManager")
    @patch("resonance_audio_builder.core.builder.asyncio.run")
    def test_start_download_flow(self, mock_async_run, mock_mgr_cls, app, tmp_path):
        # Setup mocks
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr

        csv1 = tmp_path / "test.csv"
        header = (
            "Track URI,Track Name,Artist Name,Album Name,Disc Number,"
            "Track Number,Track Duration (ms),Added By,Added At,ISRC\n"
        )
        csv1.write_text(
            f"{header}spotify:track:123,Song1,Artist1,Album1,1,1,1000,User,Date,ISRC1",
            encoding="utf-8",
        )

        # Mock user selection flow and console input
        with (
            patch.object(app, "_get_selected_csvs", return_value=[str(csv1)]),
            patch.object(app, "_select_quality"),
            patch("resonance_audio_builder.core.builder.console.input"),
        ):

            app._start_download()

            assert mock_mgr_cls.called
            assert mock_async_run.called

    def test_run_watch_mode_cli(self, app):
        with (
            patch.object(sys, "argv", ["script.py", "--watch", "CustomFolder"]),
            patch.object(app, "watch_mode") as mock_watch,
            patch("pathlib.Path.mkdir"),
        ):

            app.run()
            mock_watch.assert_called_with("CustomFolder")

    @patch("resonance_audio_builder.watch.observer.start_observer")
    def test_watch_mode(self, mock_observer, app):
        with (
            patch("os.path.exists", return_value=True),
            patch.object(app, "_select_quality"),
            patch("resonance_audio_builder.core.builder.console.print"),
        ):

            app.watch_mode("TestFolder")
            assert mock_observer.called

    def test_check_dependencies_missing_ffmpeg(self, app):
        with patch("shutil.which", return_value=None), patch("builtins.print") as mock_print:
            assert app._check_dependencies() is False
            assert mock_print.called

    def test_clear_cache_data(self, app):
        with patch("os.path.exists", return_value=True), patch("os.remove") as mock_remove:

            app._clear_cache_data()
            assert app.cache.clear.called
            assert mock_remove.call_count >= 1

    def test_notify_end(self, app):
        # Just ensure no crash
        if sys.platform == "win32":
            with patch("winsound.MessageBeep", create=True):
                app._notify_end()
        else:
            app._notify_end()
