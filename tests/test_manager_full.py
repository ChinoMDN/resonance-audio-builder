import asyncio
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from resonance_audio_builder.audio.downloader import DownloadResult
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import SearchResult
from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.exceptions import FatalError, RecoverableError
from resonance_audio_builder.core.manager import DownloadManager


class TestManagerFullCoverage:
    @pytest.fixture
    def manager(self):
        cfg = Config()
        cfg.MAX_RETRIES = 2
        # Mockeamos todo lo que se mueve
        with (
            patch("resonance_audio_builder.core.manager.RichUI"),
            patch("resonance_audio_builder.core.manager.ProgressDB"),
            patch("resonance_audio_builder.core.manager.SmartProxyManager"),
            patch("resonance_audio_builder.core.manager.AudioDownloader"),
            patch("resonance_audio_builder.core.manager.YouTubeSearcher"),
            patch("resonance_audio_builder.core.manager.MetadataWriter"),
            patch("resonance_audio_builder.core.manager.KeyboardController"),
        ):

            mgr = DownloadManager(cfg, MagicMock())
            # Use MagicMock by default to avoid AsyncMock unawaited warnings in discovery/unused tests
            mgr.searcher.search = MagicMock()
            mgr.downloader.download = MagicMock()
            mgr.state.is_done.return_value = False
            mgr.keyboard.should_quit.return_value = False
            mgr.keyboard.is_paused.return_value = False
            mgr.ui = MagicMock()
            return mgr

    @pytest.mark.asyncio
    async def test_process_track_happy_path(self, manager):
        """Camino feliz: Busca, encuentra, descarga y marca como hecho."""
        track = TrackMetadata("id1", "Song", "Artist")
        search_res = SearchResult("url", "Song", 120)

        manager.searcher.search = AsyncMock(return_value=search_res)
        # Result has bytes=1024
        manager.downloader.download = AsyncMock(return_value=DownloadResult(True, 1024))

        # Ejecutamos la lógica de procesamiento de UN track
        await manager._process_track_attempts(track, "worker_1")

        # Verificaciones
        manager.searcher.search.assert_called_once()
        manager.downloader.download.assert_called_once()
        # Mark called with bytes
        manager.state.mark.assert_called_with(track, "ok", 1024)
        manager.ui.update_main_progress.assert_called()

    @pytest.mark.asyncio
    async def test_process_track_recoverable_retry(self, manager):
        """Simula fallo recuperable que agota reintentos y luego tiene éxito."""
        track = TrackMetadata("id2", "Retry", "Artist")
        search_res = SearchResult("url", "Retry", 120)

        # Primer intento falla (Recoverable), segundo éxito
        manager.searcher.search = AsyncMock(side_effect=[RecoverableError("Network Glitch"), search_res])
        manager.downloader.download = AsyncMock(return_value=DownloadResult(True, 1024))

        # Mockeamos sleep para que el test no tarde
        with patch("asyncio.sleep", new_callable=AsyncMock):
            await manager._process_track_attempts(track, "worker_1")

        # Debe haber llamado a search 2 veces
        assert manager.searcher.search.call_count == 2
        manager.state.mark.assert_called_with(track, "ok", 1024)

    @pytest.mark.asyncio
    async def test_process_track_fatal_error(self, manager):
        """Simula error fatal (ej. no encontrado) que aborta inmediatamente."""
        track = TrackMetadata("id3", "Fatal", "Artist")

        # Search lanza error fatal
        manager.searcher.search = AsyncMock(side_effect=FatalError("Not Found anywhere"))

        await manager._process_track_attempts(track, "worker_1")

        # Solo 1 intento, no reintenta
        assert manager.searcher.search.call_count == 1
        # Check that error is recorded
        manager.state.mark.assert_called_with(track, "error", error=ANY)

    @pytest.mark.asyncio
    async def test_skip_already_done(self, manager):
        """Si ya está en DB, no debe hacer nada."""
        track = TrackMetadata("id4", "Done", "Artist")
        manager.state.is_done.return_value = True

        await manager._process_track_attempts(track, "worker_1")

        manager.searcher.search.assert_not_called()
        # Check UI update or log if applicable, depends on implementation added
        # manager.ui.add_log.assert_called()

    @pytest.mark.asyncio
    async def test_pause_logic(self, manager):
        """Verifica que el worker espere si está pausado."""
        manager.keyboard.is_paused.side_effect = [True, True, False]  # Pausa 2 ciclos, luego resume
        manager.keyboard.should_quit.side_effect = [False, False, False, True]  # Eventually quit to stop loop

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # We mock queue.get to wait or return item
            track = TrackMetadata("id5", "P", "A")

            # Important: queue is an asyncio.Queue instance, not a Mock. We must replace it or patch `get`
            manager.queue = MagicMock()
            manager.queue.get = AsyncMock(side_effect=[track, asyncio.CancelledError])
            manager.queue.task_done = MagicMock()

            # Mock process to finish quickly
            manager._process_track_attempts = AsyncMock(return_value=True)
            manager.ui.add_download_task.return_value = "t1"

            # Run worker logic
            t = asyncio.create_task(manager._worker())
            await asyncio.sleep(0.01)
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

            # Verificamos que sleep fue llamado (por la espera activa de pausa)
            assert mock_sleep.called

    @pytest.mark.asyncio
    async def test_run_flow(self, manager):
        """Test the run method execution flow using Queue mocks"""
        tracks = [TrackMetadata("id1", "T", "A"), TrackMetadata("id2", "T2", "A2")]

        # Setup mocks
        manager.state.is_done.return_value = False
        manager.state.get_stats.return_value = {"ok": 0, "skip": 0, "error": 0, "bytes": 0}
        manager.keyboard.should_quit.return_value = False

        # Mock Queue completely to avoid async loop issues
        manager.queue = MagicMock()
        # empty() returns False twice (loop runs), then True (loop stops)
        manager.queue.empty.side_effect = [False, False, True, True, True]
        # Setup mocks with pre-completed futures to avoid AsyncMock warnings
        f = asyncio.Future()
        f.set_result(None)
        manager.queue.put = MagicMock(return_value=f)
        manager.queue.join = MagicMock(return_value=f)

        # Mock Dependencies
        with (
            patch("resonance_audio_builder.core.manager.Confirm.ask", return_value=True),
            patch("resonance_audio_builder.core.manager.console.print"),
            patch("asyncio.create_task") as mock_create_task,
            patch.object(manager, "_worker", return_value=None),
            patch("asyncio.sleep", return_value=f),
        ):

            # Execute
            await manager.run(tracks)

            # Verification
            assert manager.ui.start.called
            assert manager.ui.stop.called
            # Verify workers started
            assert mock_create_task.call_count >= 1
            # Verify queue join called
            assert manager.queue.join.called
            # Verify items put in queue
            assert manager.queue.put.call_count == 2

    def test_print_batch_summary(self, manager):
        """Test the UI summary printing"""
        tracks = [TrackMetadata("id1", "Done", "A"), TrackMetadata("id2", "Pending", "B")]
        pending = [tracks[1]]

        manager.state.is_done.side_effect = lambda tid: tid == "id1"

        with (
            patch("resonance_audio_builder.core.manager.console.print") as mock_print,
            patch("resonance_audio_builder.core.manager.Panel"),
            patch("resonance_audio_builder.core.manager.Table") as mock_table,
        ):

            manager._print_batch_summary(tracks, pending)

            assert mock_print.call_count >= 2  # Queue table and Summary grid
            assert mock_table.called
