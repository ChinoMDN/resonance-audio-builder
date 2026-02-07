from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resonance_audio_builder.audio.downloader import AudioDownloader
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.exceptions import (
    CopyrightError,
    FatalError,
    GeoBlockError,
    RecoverableError,
    YouTubeError,
)


class TestAudioDownloaderExpanded:
    @pytest.fixture
    def downloader(self):
        config = MagicMock()
        config.COOKIES_FILE = "cookies.txt"
        config.MODE = "both"
        config.OUTPUT_FOLDER_HQ = "HQ"
        config.OUTPUT_FOLDER_MOBILE = "Mobile"
        config.SPECTRAL_ANALYSIS = True
        config.SPECTRAL_CUTOFF = 20000

        logger = MagicMock()
        proxy_manager = MagicMock()

        with patch("resonance_audio_builder.audio.downloader.validate_cookies_file", return_value=True):
            dl = AudioDownloader(config, logger, proxy_manager)
            dl.analyzer = MagicMock()
            return dl

    @pytest.mark.asyncio
    async def test_download_no_search_result(self, downloader):
        track = MagicMock()
        track.title = "Test Song"

        # Ensure we don't skip due to existing files
        with (
            patch.object(downloader, "_prepare_download_paths", return_value=(Path("h"), Path("m"), True, True)),
            patch.object(downloader, "_check_existing_files", return_value=(False, False)),
        ):

            result = await downloader.download(None, track)
            assert not result.success
            assert "No search result" in result.error

    @pytest.mark.asyncio
    async def test_download_raw_failure(self, downloader):
        track = MagicMock()
        search_result = SearchResult(url="http://url", title="title", duration=60)

        with patch.object(downloader, "_prepare_download_paths") as mock_prep:
            # Needed HQ and Mobile, not existing
            mock_prep.return_value = (Path("hq.m4a"), Path("mob.m4a"), True, True)

            with (
                patch.object(downloader, "_check_existing_files", return_value=(False, False)),
                patch.object(downloader, "_download_raw", side_effect=Exception("Raw Download Failed")),
            ):

                result = await downloader.download(search_result, track)
                assert not result.success
                assert "Raw Download Failed" in result.error

    def test_handle_ytdlp_error(self, downloader):
        # 429 Error
        with patch("time.sleep"), pytest.raises(RecoverableError):
            downloader._handle_ytdlp_error(Exception("HTTP Error 429: Too Many Requests"), None)

        # Copyright
        with pytest.raises(CopyrightError):
            downloader._handle_ytdlp_error(Exception("Copyright claim by SME"), None)

        # Geo
        with pytest.raises(GeoBlockError):
            downloader._handle_ytdlp_error(Exception("Video not available in your country"), None)

        # Login
        with pytest.raises(FatalError):
            downloader._handle_ytdlp_error(Exception("Sign in to confirm your age"), None)

        # Generic
        with pytest.raises(YouTubeError):
            downloader._handle_ytdlp_error(Exception("Unknown error"), None)

    @pytest.mark.asyncio
    async def test_transcoding_pipeline_partial_success(self, downloader):
        downloader.cfg.QUALITY_HQ_BITRATE = "320"
        downloader.cfg.QUALITY_MOBILE_BITRATE = "96"

        raw = Path("raw.webm")
        hq = Path("hq.m4a")
        mob = Path("mob.m4a")
        track = MagicMock()

        # Mock transcode: HQ succeeds, Mobile fails
        async def mock_transcode(raw, out, bitrate):
            if out == hq:
                # Simulate success
                with patch.object(Path, "exists", return_value=True), patch.object(Path, "stat") as mock_stat:
                    mock_stat.return_value.st_size = 1000
                    return True
            return False

        with (
            patch.object(downloader, "_transcode", side_effect=mock_transcode),
            patch.object(downloader, "_inject_metadata", new_callable=AsyncMock) as mock_inject,
        ):

            # Mock stat for size calculation in pipeline
            with patch("pathlib.Path.stat") as pstat:
                pstat.return_value.st_size = 1024

                success, bytes_count = await downloader._perform_transcoding_pipeline(raw, hq, mob, track, True, True)

                # Success is True because at least one worked?
                # The code says if todo_hq and fails -> success=False.
                # Wait, let's check code:
                # if todo_hq: if results[idx]: ... else: success = False
                # if todo_mob: if results[idx]: ... else: success = False
                # So if ANY fail, success is False.

                assert success is False
                assert mock_inject.call_count == 1  # only HQ injected

    @pytest.mark.asyncio
    async def test_validate_audio_file_success(self, downloader):
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            process = AsyncMock()
            process.communicate.return_value = (b'{"format": {"duration": "100.0"}}', b"")
            process.returncode = 0
            mock_exec.return_value = process

            with patch.object(Path, "exists", return_value=True), patch.object(Path, "stat") as mock_stat:
                mock_stat.return_value.st_size = 100000

                valid = await downloader.validate_audio_file(Path("test.m4a"))
                assert valid is True

    @pytest.mark.asyncio
    async def test_download_skip_all_done(self, downloader):
        with patch.object(downloader, "_prepare_download_paths") as mock_prep:
            mock_prep.return_value = (Path("hq.m4a"), Path("mob.m4a"), True, True)

            with patch.object(downloader, "_check_existing_files", return_value=(True, True)):
                track = MagicMock()
                track.title = "Done Song"
                result = await downloader.download(SearchResult("u", "t", "d", "i"), track)
                assert result.success
                assert result.skipped

    def test_build_ffmpeg_cmd(self, downloader):
        downloader.cfg.NORMALIZE_AUDIO = True
        cmd = downloader._build_ffmpeg_cmd(Path("in.webm"), Path("out.m4a"), "320")
        assert any("loudnorm" in arg for arg in cmd)
        assert "320k" in cmd
        assert str(Path("out.m4a")) in cmd
