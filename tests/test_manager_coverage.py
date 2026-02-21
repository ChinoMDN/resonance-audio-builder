from unittest.mock import MagicMock, mock_open, patch

import pytest

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.manager import DownloadManager


@pytest.fixture
def manager():
    cfg = Config()
    cfg.ERROR_FILE = "error.txt"
    cfg.ERROR_CSV = "error.csv"
    cache = MagicMock()
    with (
        patch("resonance_audio_builder.core.manager.RichUI"),
        patch("resonance_audio_builder.core.manager.ProgressDB"),
        patch("resonance_audio_builder.core.manager.SmartProxyManager"),
        patch("resonance_audio_builder.core.manager.AudioDownloader"),
        patch("resonance_audio_builder.core.manager.YouTubeSearcher"),
        patch("resonance_audio_builder.core.manager.MetadataWriter"),
        patch("resonance_audio_builder.core.manager.KeyboardController"),
        patch("resonance_audio_builder.network.limiter.CircuitBreaker"),
    ):
        mgr = DownloadManager(cfg, cache)
        mgr.ui = MagicMock()
        mgr.state = MagicMock()
        return mgr


def test_save_failed_writes_files(manager):
    track = TrackMetadata(track_id="1", title="Title", artist="Artist")
    track.raw_data = {"title": "Title", "artist": "Artist"}
    track.playlist_subfolder = "Pop"
    manager.failed_tracks.append((track, "Some Error"))

    with patch("builtins.open", mock_open()) as mock_file:
        manager._save_failed()

        # Check call count: 2 opens (txt + csv)
        assert mock_file.call_count == 2
        mock_file.assert_any_call("error.txt", "w", encoding="utf-8")
        mock_file.assert_any_call("error.csv", "w", encoding="utf-8", newline="")


def test_save_failed_no_tracks(manager):
    manager.failed_tracks = []
    with patch("builtins.open", mock_open()) as mock_file:
        manager._save_failed()
        mock_file.assert_not_called()


def test_save_failed_exception_handling(manager):
    track = TrackMetadata(track_id="1", title="Title", artist="Artist")
    track.raw_data = {"title": "Title", "artist": "Artist"}
    manager.failed_tracks.append((track, "Some Error"))

    with patch("builtins.open", side_effect=PermissionError("Boom")):
        manager.log = MagicMock()
        manager._save_failed()
        manager.log.error.assert_called()
