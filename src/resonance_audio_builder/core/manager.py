import asyncio
import csv
import os
import traceback
from datetime import datetime
from typing import List, Tuple

from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from resonance_audio_builder.audio.downloader import AudioDownloader
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.tagging import MetadataWriter
from resonance_audio_builder.audio.youtube import YouTubeSearcher
from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.core.exceptions import (
    FatalError,
    RecoverableError,
)
from resonance_audio_builder.core.input import KeyboardController
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.core.state import ProgressDB
from resonance_audio_builder.core.ui import (
    RichUI,
    clear_screen,
    console,
    print_header,
)
from resonance_audio_builder.core.utils import export_m3u, save_history
from resonance_audio_builder.network.cache import CacheManager
from resonance_audio_builder.network.proxies import SmartProxyManager


class DownloadManager:
    """Orquestador principal de descargas (Async)"""

    def __init__(self, config: Config, cache_manager: CacheManager):
        self.cfg = config
        self.log = Logger(config.DEBUG_MODE)
        self.cache = cache_manager

        self.state = ProgressDB(config)
        self.ui = RichUI(config)
        self.log.set_tracker(self.ui)

        # Init Proxy Manager (Async compliant)
        self.proxy_manager = SmartProxyManager(self.cfg.PROXIES_FILE, self.cfg.USE_PROXIES)

        self.downloader = AudioDownloader(self.cfg, self.log, self.proxy_manager)
        self.searcher = YouTubeSearcher(self.cfg, self.log, self.cache, self.proxy_manager)
        self.metadata_writer = MetadataWriter(self.log)
        self.keyboard = KeyboardController(self.log)

        console.clear()
        self.queue = asyncio.Queue()
        self.failed_tracks: List[Tuple[TrackMetadata, str]] = []

    async def run(self, tracks: List[TrackMetadata]):
        """Ejecuta la descarga de todas las canciones (Async)"""
        # Filtrar ya procesadas
        pending = [t for t in tracks if not self.state.is_done(t.track_id)]

        if not pending:
            print("\n✓ ¡Todas las canciones ya están descargadas!")
            return

        clear_screen()
        print_header()
        self._print_batch_summary(tracks, pending)

        if not Confirm.ask("Start download?", default=True):
            console.print("[yellow]Cancelled by user.[/yellow]")
            return

        print()

        # Start Live Display
        self.ui.start(len(pending))

        # Fill Queue
        self.log.debug(f"filling queue with {len(pending)} items")
        for t in pending:
            await self.queue.put(t)
        self.log.debug("queue filled")

        # Start keyboard listener (Thread)
        self.keyboard.start()

        # Start Workers
        self.log.debug(f"starting {self.cfg.MAX_WORKERS} workers")
        workers = []
        for i in range(self.cfg.MAX_WORKERS):
            task = asyncio.create_task(self._worker())
            workers.append(task)
        self.log.debug("workers started")

        # Wait for queue to empty
        try:
            while not self.queue.empty():
                if self.keyboard.should_quit():
                    break
                await asyncio.sleep(0.5)

            if not self.keyboard.should_quit():
                await self.queue.join()

        except asyncio.CancelledError:
            pass
        finally:
            for w in workers:
                w.cancel()

            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except Exception:
                    break

            self.keyboard.stop()
            self.ui.stop()
            self._save_failed()
            self._print_summary()

    def _print_batch_summary(self, tracks: List[TrackMetadata], pending: List[TrackMetadata]):
        """Muestra el resumen visual de la cola de descarga"""
        table = Table(title=f"Download Queue ({len(pending)} pending)", expand=True, box=None)
        table.add_column("Track", style="bold white")
        table.add_column("Artist", style="cyan")
        table.add_column("Status", justify="right")

        done_count = 0
        for t in tracks:
            if self.state.is_done(t.track_id):
                if done_count < 10:
                    table.add_row(t.title, t.artist, "[green]✔ Downloaded[/green]")
                done_count += 1

        if done_count > 10:
            table.add_row("...", "...", f"[dim]+ {done_count - 10} more done[/dim]")

        pending_count = 0
        for t in pending:
            if pending_count < 20:
                table.add_row(t.title, t.artist, "[yellow]⏳ Pending[/yellow]")
            pending_count += 1

        if pending_count > 20:
            table.add_row("...", "...", f"[dim]+ {pending_count - 20} more pending[/dim]")

        console.print(Panel(table, border_style="blue"))

        # Summary Panel
        summary = Table.grid(expand=True, padding=(0, 2))
        summary.add_column(style="bold")
        summary.add_column()
        summary.add_row("Total Tracks:", str(len(tracks)))
        summary.add_row("Already Done:", f"[green]{done_count}[/green]")
        summary.add_row("To Download:", f"[yellow]{len(pending)}[/yellow]")
        summary.add_row("Quality Mode:", f"[magenta]{self.cfg.MODE}[/magenta]")

        console.print(Panel(summary, title="Batch Summary", border_style="green"))

    async def _process_track_attempts(self, track: TrackMetadata, task_id: str) -> bool:
        """Maneja los reintentos para una canción específica con gestión de errores detallada"""
        if self.state.is_done(track.track_id):
            self.ui.add_log(f"Track {track.title} already done. Skipping.")
            return True

        attempt = 0
        last_error = ""
        while attempt < self.cfg.MAX_RETRIES:
            if self.keyboard.should_quit():
                return False
            attempt += 1

            success, is_fatal, error = await self._attempt_download_iteration(track, task_id, attempt)
            if success:
                return True

            last_error = error
            if is_fatal:
                break

            if attempt < self.cfg.MAX_RETRIES:
                await asyncio.sleep(2 * attempt)

        if not self.keyboard.should_quit():
            self.ui.update_task_status(task_id, f"[red]Failed: {last_error}[/red]")
            self.state.mark(track, "error", error=last_error)
            self.ui.update_main_progress(1)
            self.failed_tracks.append((track, last_error))
        return False

    async def _attempt_download_iteration(
        self, track: TrackMetadata, task_id: str, attempt: int
    ) -> tuple[bool, bool, str]:
        """Realiza un único intento de búsqueda y descarga. Retorna (success, is_fatal, error_msg)"""
        try:
            # 1. Search
            self.ui.update_task_status(task_id, f"[cyan]Searching (Attempt {attempt})...[/cyan]")
            search_result = await self.searcher.search(track)

            # 2. Download
            self.ui.update_task_status(task_id, "[blue]Downloading...[/blue]")
            subfolder = getattr(track, "playlist_subfolder", "")
            result = await self.downloader.download(
                search_result,
                track,
                lambda: self.keyboard.should_quit(),
                subfolder=subfolder,
            )

            if not result.success:
                raise RecoverableError(result.error or "Unknown error")

            # Success logic
            status = "[yellow]Skipped[/yellow]" if result.skipped else "[green]Success[/green]"
            self.ui.update_task_status(task_id, status)
            self.state.mark(track, "skip" if result.skipped else "ok", result.bytes)
            self.ui.update_main_progress(1)
            return True, False, ""

        except FatalError as e:
            self.ui.update_task_status(task_id, f"[red]Error: {e}[/red]")
            return False, True, str(e)
        except RecoverableError as e:
            self.ui.update_task_status(task_id, f"[yellow]Retry: {e}[/yellow]")
            return False, False, str(e)
        except Exception as e:
            self.ui.update_task_status(task_id, f"[red]Error: {e}[/red]")
            self.log.debug(f"Unexpected error for {track.title}: {traceback.format_exc()}")
            return False, True, str(e)

    async def _worker(self):
        """Async worker modularizado"""
        while True:
            try:
                track = await self.queue.get()
                if self.keyboard.is_paused():
                    await asyncio.sleep(0.5)

                if self.keyboard.should_quit():
                    self.queue.task_done()
                    return

                if self.keyboard.should_skip():
                    self.state.mark(track, "skip")
                    self.ui.update_main_progress(1)
                    self.queue.task_done()
                    continue

                task_id = self.ui.add_download_task(track.artist, track.title)
                try:
                    await self._process_track_attempts(track, task_id)
                finally:
                    if task_id:
                        await asyncio.sleep(2.0)
                        self.ui.remove_task(task_id)
                    self.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

    def _save_failed(self):
        if not self.failed_tracks:
            return
        try:
            with open(self.cfg.ERROR_FILE, "w", encoding="utf-8") as f:
                f.write(f"CANCIONES FALLIDAS - {datetime.now()}\n\n")
                for track, error in self.failed_tracks:
                    f.write(f"• {track.artist} - {track.title}\n  Error: {error}\n\n")

            with open(self.cfg.ERROR_CSV, "w", encoding="utf-8", newline="") as f:
                if self.failed_tracks:
                    writer = csv.DictWriter(f, fieldnames=list(self.failed_tracks[0][0].raw_data.keys()))
                    writer.writeheader()
                    for track, _ in self.failed_tracks:
                        writer.writerow(track.raw_data)
        except Exception:
            pass

    def _print_summary(self):
        """Imprime resumen final con Rich"""
        # Calcular duración aproximada si start_time no es accesible
        # (Idealmente RichUI podría trackear start_time o lo pasamos)

        stats = self.state.get_stats()
        console.print("\n")
        self.ui.show_summary(stats)

        if self.failed_tracks:
            console.print(f"[yellow]Failed tracks saved to: {self.cfg.ERROR_FILE}[/yellow]")

        # Guardar historial
        session_data = {
            "date": datetime.now().isoformat(),
            "success": stats.get("ok", 0),
            "skipped": stats.get("skip", 0),
            "failed": stats.get("error", 0),
            "bytes": stats.get("bytes", 0),
            "mode": self.cfg.MODE,
        }
        if self.cfg.SAVE_HISTORY:
            save_history(self.cfg.HISTORY_FILE, session_data)

        # Exportar playlist M3U
        if self.cfg.GENERATE_M3U and stats.get("ok", 0) > 0:
            try:
                # Recopilar archivos descargados
                m3u_tracks = []
                folder = (
                    self.cfg.OUTPUT_FOLDER_HQ
                    if self.cfg.MODE != QualityMode.MOBILE_ONLY
                    else self.cfg.OUTPUT_FOLDER_MOBILE
                )
                if os.path.exists(folder):
                    for f in os.listdir(folder):
                        if f.endswith(".mp3"):
                            path = os.path.join(folder, f)
                            title = f.replace(".mp3", "")
                            m3u_tracks.append((path, title, 0))

                if m3u_tracks:
                    export_m3u(m3u_tracks, self.cfg.M3U_FILE)
                    print(f"  [i] Playlist M3U: {self.cfg.M3U_FILE}")
            except Exception:
                pass

        print("=" * 60)
