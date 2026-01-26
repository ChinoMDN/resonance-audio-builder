import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from resonance_audio_builder.audio.downloader import AudioDownloader
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config


class TestDownloaderFull:
    @pytest.fixture
    def downloader(self):
        cfg = Config()
        logger = MagicMock()
        return AudioDownloader(cfg, logger)

    @pytest.mark.asyncio
    async def test_perform_transcoding_pipeline(self, downloader):
        """Test the orchestration of transcoding tasks"""
        # Mock dependencies
        downloader._transcode = AsyncMock(return_value=True)
        downloader._inject_metadata = AsyncMock()

        raw, hq, mob = Path("raw"), Path("hq"), Path("mob")
        track = TrackMetadata("id", "t", "a")

        # Test success path
        # Mock file sizes for byte calculation
        with patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value.st_size = 100

            success, bytes_n = await downloader._perform_transcoding_pipeline(raw, hq, mob, track, True, True)

            assert success is True
            assert bytes_n == 200  # 100 + 100
            assert downloader._transcode.call_count == 2
            assert downloader._inject_metadata.call_count == 2

    def test_resize_cover(self, downloader):
        """Test cover art resizing"""
        # Create a real small test image
        img = Image.new("RGB", (100, 100), color="red")
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        original_bytes = buffer.getvalue()
        original_size = len(original_bytes)

        # Test resize to smaller dimensions
        # _resize_cover is async? In downloader.py it is `async def _resize_cover`.
        # User fix `def test_resize_cover` is sync and calls it sync?
        # Downloader code (Viewed step 418):
        # 106: async def _resize_cover(...)
        # 109: return await loop.run_in_executor(None, self._resize_cover_sync, ...)
        # 111: def _resize_cover_sync(...)

        # So I should test `_resize_cover_sync` directly if I want sync test, OR call async wrapper.
        # User fixture `downloader` in test_downloader_full uses `AudioDownloader`.
        # User code calls `downloader._resize_cover(...)`.
        # If it's async, this will return a coroutine and fail assertion.
        # I will change it to `_resize_cover_sync` which IS sync and contains the logic.

        resized_bytes = downloader._resize_cover_sync(original_bytes, max_size=50)

        # Assertions
        assert len(resized_bytes) > 0, "Resized image should not be empty"
        assert len(resized_bytes) < original_size, "Resized image should be smaller"

        # Verify it's still a valid image
        resized_img = Image.open(io.BytesIO(resized_bytes))
        assert resized_img.size[0] <= 50, "Width should be <= 50"
        assert resized_img.size[1] <= 50, "Height should be <= 50"

    @pytest.mark.asyncio
    async def test_transcode_full(self, downloader, tmp_path):
        """verify transcode logic call arguments"""
        input_file = tmp_path / "input.webm"
        input_file.touch()
        output_file = tmp_path / "output.mp3"
        output_file.write_text("data")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            process = MagicMock()
            process.communicate = AsyncMock(return_value=(b"", b""))
            process.returncode = 0
            mock_exec.return_value = process

            success = await downloader._transcode(input_file, output_file, "192")
            assert success is True
            mock_exec.assert_called()
        """Test full flow of _download_raw -> _execute_ydl"""
        track = TrackMetadata("id1", "Song", "Artist")
        dl_path = tmp_path / "downloads"
        dl_path.mkdir()

        # Mock yt_dlp
        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_ydl = mock_ydl_cls.return_value
            mock_ydl.__enter__.return_value = mock_ydl

            # Simulate download success (logs info)
            mock_ydl.extract_info.return_value = {"id": "vid1", "title": "Song"}
            mock_ydl.prepare_filename.return_value = str(dl_path / "song.webm")

            # _download_raw returns Path
            result = await downloader._download_raw("http://url", "name")

            assert isinstance(result, Path)
            mock_ydl.extract_info.assert_called()

    @pytest.mark.asyncio
    async def test_download_via_ytdlp_download_error(self, downloader):
        """Test download failure handling"""
        from resonance_audio_builder.core.exceptions import YouTubeError

        with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
            mock_ydl = mock_ydl_cls.return_value
            mock_ydl.__enter__.return_value = mock_ydl
            # Simulate error in extract_info logic wrap
            # But the test calls _execute_ydl via run_in_executor

            # Just verify _download_raw re-raises if execute_ydl fails
            with patch(
                "resonance_audio_builder.audio.downloader.AudioDownloader._execute_ydl", side_effect=Exception("Boom")
            ):
                with pytest.raises(YouTubeError):
                    await downloader._download_raw("http://url", "name")

    @pytest.mark.asyncio
    async def test_get_ytdlp_options(self, downloader):
        """Cover option generation"""
        opts = downloader._get_ytdlp_options(Path("/tmp"), "best")
        assert "outtmpl" in opts
        assert opts["format"] == "bestaudio/best"
        assert opts["geo_bypass"] is True

    @pytest.mark.asyncio
    async def test_setup_logger(self, downloader):
        """Cover logger setup"""
        logger = downloader._setup_ytdlp_logger()
        assert hasattr(logger, "debug")
        # trigger logger methods
        logger.debug("msg")
        logger.warning("msg")
        logger.error("msg")
