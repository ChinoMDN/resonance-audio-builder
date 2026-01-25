import pytest
import sys
import os
import shutil
from unittest.mock import MagicMock
from pathlib import Path

# Ensure the project root is in the path
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(root_dir, 'src'))

@pytest.fixture
def isolated_fs(tmp_path):
    """Provides an isolated filesystem for tests"""
    return tmp_path

@pytest.fixture
def sample_mp3_320k(tmp_path):
    """Creates a dummy MP3 file that simulates 320kbps"""
    # Note: Real spectral analysis needs real audio. 
    # For unit tests, we might mock analyze_integrity or use a very small real valid MP3.
    # Here we create a dummy file for file existence checks.
    f = tmp_path / "test_320.mp3"
    f.write_bytes(b"ID3" + b"\x00"*1000) # Fake header
    return f

@pytest.fixture
def fake_mp3_upscaled(tmp_path):
    """Creates a dummy MP3 file that simulates fake upscaled"""
    f = tmp_path / "fake_128_up.mp3"
    f.write_bytes(b"ID3" + b"\x00"*500)
    return f

@pytest.fixture
def mock_youtube_api():
    """Mock for yt-dlp / YouTube interactions"""
    mock = MagicMock()
    mock.extract_info.return_value = {
        "id": "test_id",
        "title": "Test Song",
        "uploader": "Test Artist",
        "duration": 180,
        "webpage_url": "https://youtube.com/watch?v=test_id"
    }
    return mock

@pytest.fixture
def mock_proxies(tmp_path):
    """Mock proxy list file"""
    f = tmp_path / "proxies.txt"
    f.write_text("http://user:pass@1.2.3.4:8080\nhttp://5.6.7.8:3128")
    return f
