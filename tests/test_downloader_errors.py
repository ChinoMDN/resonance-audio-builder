import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from resonance_audio_builder.audio.downloader import AudioDownloader, DownloadResult
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.exceptions import DownloadError

class TestDownloaderFailures:
    @pytest.fixture
    def downloader(self, tmp_path):
        cfg = Config()
        cfg.OUTPUT_FOLDER_HQ = str(tmp_path / "HQ")
        cfg.OUTPUT_FOLDER_MOBILE = str(tmp_path / "Mobile")
        return AudioDownloader(cfg, MagicMock())

    @pytest.mark.asyncio
    async def test_download_yt_dlp_critical_failure(self, downloader):
        """Simula un fallo crítico de yt-dlp que no se puede reintentar"""
        search_res = SearchResult("vid", "Title", 100) # Removed 'url' based on previous finding, wait SearchResult signature
        track = TrackMetadata("id1", "Title", "Artist")

        # Simulamos que _download_raw lanza una excepción
        with patch.object(downloader, "_download_raw", side_effect=DownloadError("Critical YT Error")):
            res = await downloader.download(search_res, track)
            
            assert res.success is False
            assert "Critical YT Error" in str(res.error)

    @pytest.mark.asyncio
    async def test_transcode_ffmpeg_failure(self, downloader, tmp_path):
        """Simula que FFmpeg falla al convertir"""
        # Crear archivo dummy de entrada
        input_f = tmp_path / "temp.webm"
        input_f.touch()
        output_f = tmp_path / "out.mp3"
        
        # Simulamos fallo en subprocess (returncode != 0)
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"FFmpeg Error"))
        
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            # Llamamos a _transcode directamente para probar su lógica de error
            result = await downloader._transcode(input_f, output_f, "320")
            assert result is False

    @pytest.mark.asyncio
    async def test_download_cleanup_on_failure(self, downloader, tmp_path):
        """Verifica que se limpien los archivos temporales si algo falla"""
        track = TrackMetadata("id3", "Title", "Artist")
        temp_file = tmp_path / "temp_fail.webm"
        temp_file.touch() # Creamos el archivo "basura"
        
        # Simulamos que _download_raw devuelve este archivo, pero luego transcode falla
        with patch.object(downloader, "_download_raw", return_value=temp_file), \
             patch.object(downloader, "_transcode", return_value=False): # Transcode falla
            
            await downloader.download(SearchResult("v", "t", 100), track)
            
            # El archivo temporal debería haber sido borrado por el bloque finally/except
            assert not temp_file.exists()
