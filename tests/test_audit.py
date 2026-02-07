from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.audio.audit import AudioAuditor


class TestAudioAuditor:
    @pytest.fixture
    def auditor(self):
        return AudioAuditor(MagicMock())

    def test_audit_folder_basic(self, auditor, tmp_path):
        # Create dummy structure
        hq_dir = tmp_path / "HQ"
        hq_dir.mkdir()
        track1 = hq_dir / "test1.m4a"
        track1.write_bytes(b"dummy")

        with patch("resonance_audio_builder.audio.audit.MP4") as mock_mp4:
            # Mock MP4 tags
            mock_audio = MagicMock()
            mock_audio.keys.return_value = ["\xa9nam", "\xa9ART", "covr", "\xa9lyr"]
            mock_audio.__contains__.side_effect = lambda k: k in ["\xa9nam", "\xa9ART", "covr", "\xa9lyr"]
            mock_mp4.return_value = mock_audio

            res = auditor._audit_folder(hq_dir, check_spectral=False)

            assert res.total_files == 1
            assert res.total_size_bytes == 5
            assert len(res.missing_metadata) == 0
            assert len(res.missing_covers) == 0
            assert len(res.missing_lyrics) == 0

    def test_audit_folder_missing_tags(self, auditor, tmp_path):
        hq_dir = tmp_path / "HQ"
        hq_dir.mkdir()
        track1 = hq_dir / "missing.m4a"
        track1.write_bytes(b"dummy")

        with patch("resonance_audio_builder.audio.audit.MP4") as mock_mp4:
            mock_audio = MagicMock()
            # Missing everything
            mock_audio.keys.return_value = []
            mock_audio.__contains__.return_value = False
            mock_mp4.return_value = mock_audio

            res = auditor._audit_folder(hq_dir, check_spectral=False)

            assert res.total_files == 1
            assert len(res.missing_metadata) == 1
            assert len(res.missing_covers) == 1
            assert len(res.missing_lyrics) == 1

    def test_audit_folder_spectral(self, auditor, tmp_path):
        hq_dir = tmp_path / "HQ"
        hq_dir.mkdir()
        track1 = hq_dir / "fake.m4a"
        track1.write_bytes(b"dummy")

        with patch("resonance_audio_builder.audio.audit.MP4"):
            with patch.object(auditor.analyzer, "analyze_integrity", return_value=False):
                res = auditor._audit_folder(hq_dir, check_spectral=True)
                assert len(res.fake_hq_detected) == 1
                assert res.fake_hq_detected[0] == "fake.m4a"

    def test_scan_library_integration(self, auditor, tmp_path):
        hq_dir = tmp_path / "HQ"
        hq_dir.mkdir()
        mob_dir = tmp_path / "MOB"
        mob_dir.mkdir()

        (hq_dir / "hq.m4a").touch()
        (mob_dir / "mob.m4a").touch()

        with patch("resonance_audio_builder.audio.audit.MP4"):
            results = auditor.scan_library(hq_dir, mob_dir)
            assert "HQ" in results
            assert "Mobile" in results
            assert results["HQ"].total_files == 1
            assert results["Mobile"].total_files == 1
