import pytest
from unittest.mock import MagicMock, patch
from resonance_audio_builder.audio.analysis import AudioAnalyzer

class TestAudioAnalyzer:
    """Tests for Fake HQ detection and audio analysis"""

    @pytest.fixture
    def analyzer(self):
        return AudioAnalyzer(MagicMock())

    # --- Basic Cases ---
    def test_analyze_genuine_320kbps(self, analyzer, sample_mp3_320k):
        """Genuine 320kbps file should pass"""
        with patch("subprocess.run") as mock_run:
            # Simulate high RMS (-50dB is > -75dB threshold) => Genuine
            mock_run.return_value = MagicMock(stderr="[Parsed_astats] Overall.RMS_level=-50.0")
            assert analyzer.analyze_integrity(sample_mp3_320k, 20000) is True

    def test_analyze_fake_upscaled_128k(self, analyzer, fake_mp3_upscaled):
        """128k upscaled to 320k should fail"""
        with patch("subprocess.run") as mock_run:
             # Simulate low RMS (-80dB is < -75dB threshold) => Fake
            mock_run.return_value = MagicMock(stderr="Overall.RMS_level=-80.0")
            assert analyzer.analyze_integrity(fake_mp3_upscaled, 20000) is False

    def test_analyze_missing_file(self, analyzer, tmp_path):
        """Missing file should return False"""
        missing = tmp_path / "missing.mp3"
        assert analyzer.analyze_integrity(missing, 20000) is False

    def test_analyze_corrupted_file(self, analyzer, tmp_path):
        """Corrupted file should return True (fail open) as per implementation"""
        corrupted = tmp_path / "corrupt.mp3"
        corrupted.write_bytes(b"Garbage data")
        
        # Real code catches Exception and returns True (Innocent until proven guilty)
        with patch("subprocess.run", side_effect=Exception("FFmpeg error")):
             assert analyzer.analyze_integrity(corrupted, 20000) is True

    def test_analyze_with_custom_cutoff(self, analyzer, sample_mp3_320k):
        """Custom cutoff should be passed to ffmpeg"""
        with patch("subprocess.run") as mock_run:
             mock_run.return_value = MagicMock(stderr="Overall.RMS_level=-50.0")
             analyzer.analyze_integrity(sample_mp3_320k, 15000)
             
             assert mock_run.called
             args = mock_run.call_args[0][0] # cmd list
             assert any("highpass=f=15000" in arg for arg in args)

    # --- Edge Cases ---
    def test_analyze_flac_lossless(self, analyzer, tmp_path):
        """FLAC files should pass"""
        flac = tmp_path / "test.flac"
        flac.touch()
        with patch("subprocess.run") as mock_run:
             mock_run.return_value = MagicMock(stderr="Overall.RMS_level=-40.0")
             assert analyzer.analyze_integrity(flac, 20000) is True

    def test_analyze_silence_file(self, analyzer, sample_mp3_320k):
        """Silence file (low RMS) should be flagged"""
        with patch("subprocess.run") as mock_run:
             mock_run.return_value = MagicMock(stderr="Overall.RMS_level=-95.0")
             assert analyzer.analyze_integrity(sample_mp3_320k, 20000) is False

    @pytest.mark.parametrize("rms_level,expected", [
        ("-90.0", False), # Too quiet -> Fake
        ("-60.0", True),  # Loud -> Genuine
    ])
    def test_rms_threshold_boundaries(self, analyzer, sample_mp3_320k, rms_level, expected):
         with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stderr=f"Overall.RMS_level={rms_level}")
            assert analyzer.analyze_integrity(sample_mp3_320k, 20000) is expected
