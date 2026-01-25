import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from resonance_audio_builder.audio.analysis import AudioAnalyzer
from resonance_audio_builder.core.logger import Logger

class TestAudioAnalyzer:
    def test_analyze_integrity_integration(self):
        """Mocked test for analyzing integrity"""
        # Mock logger
        logger = Mock(spec=Logger)
        analyzer = AudioAnalyzer(logger)
        
        # Mock subprocess to return specific stderr output
        # Also mock Path.exists to pass the initial check
        with patch("subprocess.run") as mock_run, \
             patch("pathlib.Path.exists", return_value=True):
            
            # Case 1: Genuine HQ (High RMS in HF)
            mock_run.return_value.stderr = "Overall.RMS_level=-50.5"
            assert analyzer.analyze_integrity(Path("dummy.mp3")) == True
            
            # Case 2: Fake HQ (Low RMS in HF)
            mock_run.return_value.stderr = "Overall.RMS_level=-90.0"
            assert analyzer.analyze_integrity(Path("dummy.mp3")) == False
            
            # Case 3: Error
            mock_run.side_effect = Exception("FFmpeg error")
            assert analyzer.analyze_integrity(Path("dummy.mp3")) == True # Safe fallback

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
