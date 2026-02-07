import os
import pytest
from unittest.mock import MagicMock, patch
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
    
    # Create structure
    (output_folder / playlist_name).mkdir(parents=True)
    
    # Create fake file
    fake_file = output_folder / playlist_name / "Track - Artist.m4a"
    fake_file.touch()

    tracks_map = {playlist_name: [mock_track]}

    export_playlist_m3us(tracks_map, str(output_folder))

    m3u_file = output_folder / playlist_name / f"{playlist_name}.m3u8"
    assert m3u_file.exists()
    
    content = m3u_file.read_text(encoding="utf-8")
    assert "#EXTM3U" in content
    assert "Track - Artist.m4a" in content

def test_export_playlist_m3us_missing_file(tmp_path, mock_track):
    # File does not exist, should not appear in m3u
    output_folder = tmp_path / "Audio_HQ"
    playlist_name = "MyPlaylist"
    
    tracks_map = {playlist_name: [mock_track]}

    export_playlist_m3us(tracks_map, str(output_folder))

    m3u_file = output_folder / playlist_name / f"{playlist_name}.m3u8"
    # It might create an empty file or nothing. The code says:
    # if m3u_tracks: export_m3u(...)
    # So if no tracks found, no file created?
    assert not m3u_file.exists()

def test_export_playlist_m3us_empty_map(tmp_path):
    export_playlist_m3us({}, str(tmp_path))
    assert len(list(tmp_path.iterdir())) == 0

def test_export_playlist_m3us_exception():
    # Force an exception (e.g. invalid path)
    # The function catches exceptions and passes
    export_playlist_m3us({"list": []}, 12345) # Invalid path type
