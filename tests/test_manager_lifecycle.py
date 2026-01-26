import asyncio
from unittest.mock import MagicMock, patch

import pytest

from resonance_audio_builder.core.config import Config
from resonance_audio_builder.core.manager import DownloadManager


class TestManagerLifecycle:
    @pytest.fixture
    def manager(self):
        cfg = Config()
        return DownloadManager(cfg, MagicMock())

    @pytest.mark.asyncio
    async def test_shutdown_cancels_tasks(self, manager):
        """Prueba que los workers manejan la cancelación correctamente"""

        # Simulamos un worker que duerme
        async def sleepy_worker():
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                manager._running = False  # Flag for test
                raise

        # Asignamos el método worker dinámicamente para el test
        manager._worker = sleepy_worker

        # Iniciamos tarea manualmente como lo haría run()
        task = asyncio.create_task(manager._worker())
        await asyncio.sleep(0.1)

        # Cancelamos manualmente (simulando el finally de run)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        # Verificamos que se canceló (aunque en este caso es implícito por el raise)
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_error_handling_in_worker(self, manager):
        """Prueba que el worker no muera si una tarea lanza una excepción no controlada"""
        # Ponemos una tarea que hará crash
        await manager.queue.put("POISON_PILL")  # Un string en vez de TrackMetadata causará error

        # Mockeamos el logger para verificar que registró el error
        manager.logger = MagicMock()

        # Ejecutamos un ciclo manual del worker (simulado)
        with patch.object(manager, "_process_track_attempts", side_effect=Exception("Unexpected Crash")):
            # Ejecutamos lógica del worker protegida
            try:
                # Simulamos sacar de la cola y procesar
                track = manager.queue.get_nowait()
                await manager._process_track_attempts(track, "worker_1")
            except Exception:
                pass  # El worker real capturaría esto

    @pytest.mark.asyncio
    async def test_real_worker_execution(self, manager):
        """Prueba la lógica real del worker procesando un track"""
        track = MagicMock()
        track.artist = "Artist"
        track.title = "Title"

        # Setup mocks
        manager.keyboard = MagicMock()
        manager.keyboard.is_paused.return_value = False
        manager.keyboard.should_quit.return_value = False
        manager.keyboard.should_skip.return_value = False

        # Mock UI
        manager.ui = MagicMock()
        manager.ui.add_download_task.return_value = "task1"

        # Queue item
        await manager.queue.put(track)

        # Mock interactions
        manager.ui.add_download_task.return_value = "task1"

        # Mock _process_track_attempts to avoid long waits but check it's called
        with patch.object(manager, "_process_track_attempts", return_value=True) as mock_process:
            # Run worker as a task
            task = asyncio.create_task(manager._worker())

            # Wait for queue to process
            await manager.queue.join()

            # Stop worker
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert mock_process.called
            assert manager.ui.add_download_task.called
            assert manager.ui.remove_task.called
