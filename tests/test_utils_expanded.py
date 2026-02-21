from unittest.mock import MagicMock

import pytest

from resonance_audio_builder.core.utils import export_playlist_m3us


@pytest.fixture
def mock_track():
    track = MagicMock()
    track.safe_filename = "Track - Artist"
    track.artist = "Artist"
    track.title = "Track"
    track.duration_seconds = 120
    track.playlist_subfolder = "MyPlaylist"
    return track


def test_export_playlist_m3us_success(tmp_path, mock_track):
    output_folder = tmp_path / "Audio_HQ"
    playlist_name = "MyPlaylist"

    # Create base
    output_folder.mkdir(parents=True)

    tracks_map = {playlist_name: [mock_track]}

    export_playlist_m3us(tracks_map, str(output_folder))

    # M3U8 should be in the ROOT of output_folder
    m3u_file = output_folder / f"{playlist_name}.m3u8"
    assert m3u_file.exists()

    content = m3u_file.read_text(encoding="utf-8")
    assert "#EXTM3U" in content
    # Should contain path with forward slash
    assert "MyPlaylist/Track - Artist.m4a" in content


def test_export_playlist_m3us_includes_missing_file(tmp_path, mock_track):
    # Even if file does not exist, it should appear in m3u now
    output_folder = tmp_path / "Audio_HQ"
    playlist_name = "MyPlaylist"

    tracks_map = {playlist_name: [mock_track]}

    export_playlist_m3us(tracks_map, str(output_folder))

    m3u_file = output_folder / f"{playlist_name}.m3u8"
    assert m3u_file.exists()
    content = m3u_file.read_text(encoding="utf-8")
    assert "MyPlaylist/Track - Artist.m4a" in content


def test_export_playlist_m3us_empty_map(tmp_path):
    export_playlist_m3us({}, str(tmp_path))
    assert len(list(tmp_path.iterdir())) == 0


def test_export_playlist_m3us_exception():
    # Force an exception (e.g. invalid path)
    # The function catches exceptions and passes
    export_playlist_m3us({"list": []}, 12345)  # Invalid path type
