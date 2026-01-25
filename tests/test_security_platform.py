import pytest
import os
import sys
from resonance_audio_builder.audio.metadata import TrackMetadata

class TestSecurityConcerns:
    def test_filename_path_traversal_attack(self):
        """Checking for path traversal attempts"""
        t = TrackMetadata("id1", "../../../etc/passwd", "Hacker")
        # safe_filename should strip ..
        assert ".." not in t.safe_filename
        assert "/" not in t.safe_filename

    def test_command_injection_in_filename(self):
        """Checking for shell characters"""
        t = TrackMetadata("id2", "; rm -rf /", "Hacker")
        assert ";" not in t.safe_filename

class TestCrossPlatform:
    @pytest.mark.skipif(os.name != 'nt', reason="Windows specific")
    def test_windows_reserved_filenames(self):
        """CON, AUX should be mapped"""
        t = TrackMetadata("id3", "CON", "Artist")
        assert t.safe_filename != "CON"

    def test_path_compatibility(self):
        """Paths should use correct separators"""
        # Just generic check
        import pathlib
        p = pathlib.Path("a/b")
        assert str(p) == f"a{os.sep}b"
