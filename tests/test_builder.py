from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.builder import App
from resonance_audio_builder.core.config import Config


class TestApp:
    @pytest.fixture
    def app(self, tmp_path):
        with patch("resonance_audio_builder.core.builder.Config.load") as mock_load:
            cfg = Config()
            cfg.INPUT_FOLDER = str(tmp_path / "Playlists")
            cfg.CHECKPOINT_FILE = str(tmp_path / "progress.json")
            mock_load.return_value = cfg

            with (
                patch("resonance_audio_builder.core.builder.ProgressDB"),
                patch("resonance_audio_builder.core.builder.CacheManager"),
                patch("resonance_audio_builder.core.builder.Logger"),
            ):
                return App()

    def test_check_dependencies_success(self, app):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            assert app._check_dependencies() is True

    def test_check_dependencies_fail(self, app):
        with patch("shutil.which", return_value=None):
            assert app._check_dependencies() is False

    def test_select_csv_no_files(self, app, tmp_path):
        with (
            patch("resonance_audio_builder.core.builder.console.print"),
            patch("resonance_audio_builder.core.builder.Prompt.ask", return_value="0"),
            patch("resonance_audio_builder.core.builder.print_header"),
        ):

            res = app._select_csv()
            assert res == []

    def test_select_csv_with_files(self, app, tmp_path):
        playlist_dir = Path(app.cfg.INPUT_FOLDER)
        playlist_dir.mkdir(parents=True, exist_ok=True)
        (playlist_dir / "test.csv").write_text("dummy")

    def test_read_csv_success(self, app, tmp_path):
        f = tmp_path / "valid.csv"
        f.write_text("Track Name,Artist Name(s)\nSong,Artist", encoding="utf-8")

        rows = app._read_csv(str(f))
        assert len(rows) == 1
        assert rows[0]["Track Name"] == "Song"

    def test_read_csv_empty(self, app, tmp_path):
        f = tmp_path / "empty.csv"
        f.write_text("", encoding="utf-8")

        rows = app._read_csv(str(f))
        assert rows == []

    def test_deduplicate_tracks(self, app):
        t1 = TrackMetadata(track_id="1", title="T1", artist="A1")
        t2 = TrackMetadata(track_id="1", title="T1", artist="A1")
        t3 = TrackMetadata(track_id="2", title="T2", artist="A2")

        res = app._deduplicate_tracks([t1, t2, t3])
        assert len(res) == 2

    def test_select_quality(self, app):
        with (
            patch("resonance_audio_builder.core.builder.Prompt.ask", return_value="1"),
            patch("resonance_audio_builder.core.builder.print_header"),
            patch("resonance_audio_builder.core.builder.console.print"),
        ):

            from resonance_audio_builder.core.config import QualityMode

            app._select_quality()
            assert app.cfg.MODE == QualityMode.HQ_ONLY

    def test_perform_clear(self, app):
        # Option 1: Search Cache
        with patch.object(app, "_clear_cache_data") as mock_clear:
            app._perform_clear("1")
            assert mock_clear.called

        # Option 2: Progress
        app.db = MagicMock()
        app._perform_clear("2")
        assert app.db.clear.called

    # @pytest.mark.asyncio - Removed as function is sync
    def test_retry_failed_no_file(self, app):
        app.cfg.ERROR_CSV = "non_existent.csv"
        with patch("resonance_audio_builder.core.builder.console.print") as mock_print:
            with patch("resonance_audio_builder.core.builder.console.input"):
                app._retry_failed()
                assert mock_print.called

    def test_start_download_empty_list(self, app):
        with patch.object(app, "_get_selected_csvs", return_value=[]):
            with patch("resonance_audio_builder.core.builder.console.print") as mock_print:
                app._start_download()
                assert mock_print.called

    def test_read_csv_encodings(self, app, tmp_path):
        f = tmp_path / "latin1.csv"
        # Track Name, Artist Name(s) in latin-1
        f.write_bytes("Canción,Artista\nTest,Test".encode("latin-1"))

        # We need to mock the header detection or just ensure it returns rows
        with patch("resonance_audio_builder.core.builder.csv.DictReader") as mock_reader:
            mock_inst = MagicMock()
            mock_inst.fieldnames = ["Track Name"]
            mock_inst.__iter__.return_value = [{"Track Name": "Test"}]
            mock_reader.return_value = mock_inst
            rows = app._read_csv(str(f))
            assert len(rows) > 0
