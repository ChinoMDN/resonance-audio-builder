import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resonance_audio_builder.audio.downloader import AudioDownloader, DownloadResult
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.config import Config


class TestAudioDownloader:
    @pytest.fixture
    def downloader(self):
        cfg = Config()
        logger = MagicMock()
        return AudioDownloader(cfg, logger)

    @pytest.mark.asyncio
    async def test_validate_audio_file_success(self, downloader, tmp_path):
        f = tmp_path / "valid.mp3"
        f.write_bytes(b"\x00" * 100000)  # Mock large enough file

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(json.dumps({"format": {"duration": "180"}}).encode(), b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            res = await downloader.validate_audio_file(f)
            assert res is True

    @pytest.mark.asyncio
    async def test_validate_audio_file_invalid(self, downloader, tmp_path):
        f = tmp_path / "corrupt.mp3"
        f.write_bytes(b"\x00" * 100)  # Too small

        res = await downloader.validate_audio_file(f)
        assert res is False

    @pytest.mark.asyncio
    async def test_download_skip_if_exists(self, downloader, tmp_path):
        # Setup paths
        from resonance_audio_builder.core.config import QualityMode

        downloader.cfg.MODE = QualityMode.HQ_ONLY
        downloader.cfg.OUTPUT_FOLDER_HQ = str(tmp_path / "HQ")
        track = TrackMetadata(track_id="1", title="Title", artist="Artist")
        search_res = SearchResult("url", "Title", 180)

        # Determine the expected path
        hq_folder = Path(downloader.cfg.OUTPUT_FOLDER_HQ)
        hq_folder.mkdir(parents=True, exist_ok=True)
        output_file = hq_folder / f"{track.safe_filename}.mp3"
        output_file.write_bytes(b"\x00" * 100000)

        # Mock validate_audio_file to return True (existing file is valid)
        with patch.object(downloader, "validate_audio_file", return_value=True):
            res = await downloader.download(search_res, track, lambda: False, subfolder="")
            assert isinstance(res, DownloadResult)
            assert res.success is True
            assert res.skipped is True

    @pytest.mark.asyncio
    async def test_transcode_mp3(self, downloader, tmp_path):
        input_f = tmp_path / "input.webm"
        input_f.write_bytes(b"dummy content")
        output_f = tmp_path / "output.mp3"

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        # We need to simulate the file being created by ffmpeg
        def create_output(*args, **kwargs):
            output_f.write_bytes(b"mocked mp3")
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=create_output) as mock_exec:
            res = await downloader._transcode(input_f, output_f, bitrate="320")
            assert res is True
            assert mock_exec.called

    def test_get_ytdlp_options(self, downloader):
        out_tmpl = Path("test.%(ext)s")
        proxy = "http://proxy:8080"
        downloader._cookies_valid = True
        downloader.cfg.COOKIES_FILE = "cookies.txt"

        opts = downloader._get_ytdlp_options(out_tmpl, proxy)
        assert opts["proxy"] == proxy
        assert opts["cookiefile"] == "cookies.txt"
        assert opts["outtmpl"] == str(out_tmpl)

    def test_handle_ytdlp_error_retryable(self, downloader):
        from resonance_audio_builder.core.exceptions import RecoverableError

        e = Exception("HTTP Error 429: Too Many Requests")

        with patch("time.sleep"):  # Don't actually sleep
            with pytest.raises(RecoverableError):
                downloader._handle_ytdlp_error(e, None)

    def test_handle_ytdlp_error_fatal(self, downloader):
        from resonance_audio_builder.core.exceptions import CopyrightError

        e = Exception("This video contains content from... copyright")

        with pytest.raises(CopyrightError):
            downloader._handle_ytdlp_error(e, None)

    def test_build_ffmpeg_cmd(self, downloader):
        in_p = Path("in.webm")
        out_p = Path("out.mp3")
        downloader._build_ffmpeg_cmd(in_p, out_p, "320")

    @pytest.mark.asyncio
    async def test_check_fake_hq(self, downloader, tmp_path):
        downloader.cfg.SPECTRAL_ANALYSIS = True
        downloader.analyzer = MagicMock()
        downloader.analyzer.analyze_integrity.return_value = False

        raw_f = tmp_path / "raw.webm"
        raw_f.write_bytes(b"data")
        track = TrackMetadata(track_id="1", title="T1", artist="A1")

        res = downloader._check_fake_hq(raw_f, track, needed_hq=True)
        assert res is True  # It is fake

    @pytest.mark.asyncio
    async def test_fetch_metadata_assets(self, downloader):
        track = TrackMetadata(track_id="1", title="T1", artist="A1")
        track.cover_url = "http://url"

        with (
            patch.object(downloader, "_download_cover", AsyncMock(return_value=b"IMG")),
            patch.object(downloader, "_resize_cover", AsyncMock(return_value=b"IMG2")),
        ):
            await downloader._fetch_metadata_assets(track)
            assert track.cover_data == b"IMG2"

    def test_handle_ytdlp_error_geo(self, downloader):
        from resonance_audio_builder.core.exceptions import GeoBlockError

        e = Exception("This video is not available in your country")
        with pytest.raises(GeoBlockError):
            downloader._handle_ytdlp_error(e, None)
