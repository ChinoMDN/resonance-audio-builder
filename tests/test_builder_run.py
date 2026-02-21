from unittest.mock import patch

import pytest

from resonance_audio_builder.core.builder import App


class TestAppFull:
    @pytest.fixture
    def app(self):
        # We still need to mock ProgressDB to avoid DB errors during init
        with patch("resonance_audio_builder.core.builder.ProgressDB"):
            return App()

    def test_run_watch_mode(self, app, tmp_path):
        """Test watch mode initialization"""
        with patch("resonance_audio_builder.watch.observer.start_observer") as mock_observer:
            with patch.object(app, "_select_quality"):
                # Test that watch_mode calls start_observer
                app.watch_mode(str(tmp_path))
                mock_observer.assert_called_once()

    def test_run_cli_args(self, app):
        """Test CLI argument parsing"""
        with (
            patch("sys.argv", ["main.py", "--watch", "d:/music"]),
            patch("pathlib.Path.mkdir"),
            patch.object(app, "watch_mode") as mock_watch,
        ):

            app.run()
            mock_watch.assert_called_with("d:/music")

    def test_start_download_flow_sync(self, app, tmp_path):
        """Test internal download flow logic (Sync wrapper)"""
        # Create dummy CSV
        csv_file = tmp_path / "test.csv"
        header = (
            "Track URI,Track Name,Artist Name,Album Name,Disc Number,"
            "Track Number,Track Duration (ms),Added By,Added At,ISRC\n"
        )
        csv_file.write_text(
            f"{header}spotify:track:123,Song1,Artist1,Album1,1,1,1000,User,Date,ISRC1",
            encoding="utf-8",
        )
        # We must mock asyncio.run because _start_download calls it
        # Also mock builtins.input for rich console inputs
        with patch("resonance_audio_builder.core.builder.asyncio.run") as mock_async_run, patch("builtins.input"):
            with patch.object(app, "_select_quality"):
                with (
                    patch("resonance_audio_builder.core.builder.console.input"),
                    patch("resonance_audio_builder.core.builder.console.print"),
                ):

                    with patch("resonance_audio_builder.core.builder.DownloadManager") as mock_mgr_cls:

                        app._start_download([str(csv_file)], ask_quality=False)

                        mock_async_run.assert_called()
                        assert mock_mgr_cls.called

    def test_check_dependencies(self, app):
        """Test dependency checking"""
        with patch("shutil.which", return_value=None):
            assert app._check_dependencies() is False

        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert app._check_dependencies() is True
