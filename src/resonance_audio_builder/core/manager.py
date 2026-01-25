import os
import queue
import threading
import time
import traceback
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.core.state import RichProgressTracker
from resonance_audio_builder.core.exceptions import FatalError, RecoverableError
from resonance_audio_builder.core.ui import print_header, clear_screen, format_time, format_size, console
from resonance_audio_builder.core.utils import save_history, export_m3u
from resonance_audio_builder.core.input import KeyboardController
from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.audio.youtube import YouTubeSearcher
from resonance_audio_builder.audio.downloader import AudioDownloader
from resonance_audio_builder.audio.tagging import MetadataWriter
from resonance_audio_builder.network.cache import CacheManager
from resonance_audio_builder.network.proxies import ProxyManager

class DownloadManager:
    """Orquestador principal de descargas"""

    def __init__(self, config: Config, cache_manager: CacheManager):
        self.cfg = config
        self.log = Logger(config.DEBUG_MODE)
        self.cache = cache_manager
        self.tracker = RichProgressTracker(self.cfg)
        self.log.set_tracker(self.tracker)  # Link logger to tracker UI
        
        # Init Proxy Manager
        self.proxy_manager = ProxyManager(self.cfg.PROXIES_FILE, self.cfg.USE_PROXIES)
        
        self.downloader = AudioDownloader(self.cfg, self.log, self.proxy_manager)
        self.searcher = YouTubeSearcher(self.cfg, self.log, self.cache, self.proxy_manager)
        self.metadata_writer = MetadataWriter(self.log)
        self.keyboard = KeyboardController(self.log)

        # Limpiar terminal al inicio
        console.clear()
        self.queue: queue.Queue = queue.Queue()
        self.failed_tracks: List[Tuple[TrackMetadata, str]] = []
        self._print_lock = threading.Lock()

    def run(self, tracks: List[TrackMetadata]):
        """Ejecuta la descarga de todas las canciones"""

        # Filtrar ya procesadas
        pending = [t for t in tracks if not self.tracker.is_done(t.track_id)]

        if not pending:
            print("\n✓ ¡Todas las canciones ya están descargadas!")
            return

        clear_screen()
        print_header()

        self.tracker.total_pending = len(pending)
        self.tracker.reset_stats()

        # Mostrar info de canciones
        table = Table(title=f"Download Queue ({len(pending)} pending)", expand=True, box=None)
        table.add_column("Track", style="bold white")
        table.add_column("Artist", style="cyan")
        table.add_column("Status", justify="right")

        # Mostrar primero las ya descargadas (primeras 10)
        done_count = 0
        for t in tracks:
            if self.tracker.is_done(t.track_id):
                if done_count < 10:
                    table.add_row(t.title, t.artist, "[green]✔ Downloaded[/green]")
                done_count += 1

        if done_count > 10:
            table.add_row("...", "...", f"[dim]+ {done_count - 10} more done[/dim]")

        # Mostrar las pendientes (primeras 20)
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

        if not Confirm.ask("Start download?", default=True):
            console.print("[yellow]Cancelled by user.[/yellow]")
            return

        print()

        # Start Live Display
        self.tracker.start(len(pending))

        # Llenar cola
        for t in pending:
            self.queue.put(t)

        # Iniciar keyboard listener
        self.keyboard.start()

        # Iniciar workers
        workers = []
        for i in range(self.cfg.MAX_WORKERS):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            workers.append(t)

        # Esperar finalización
        try:
            while not self.queue.empty() and not self.keyboard.should_quit():
                time.sleep(0.5)

            # Vaciar cola si salimos prematuramente
            if self.keyboard.should_quit():
                while not self.queue.empty():
                    try:
                        self.queue.get_nowait()
                        self.queue.task_done()
                    except:
                        break

            self.queue.join()

        except KeyboardInterrupt:
            # Quit handled by signal in App or here
            self.keyboard.quit_event.set()

        finally:
            self.keyboard.stop()
            self.tracker.stop()  # Stop Live display
            self.tracker.save()
            self._save_failed()
            self._print_summary()

    def _worker(self):
        """Thread worker de descarga"""
        while not self.keyboard.should_quit():
            try:
                track = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            if track is None:
                self.queue.task_done()
                break

            # Esperar si está pausado
            self.keyboard.wait_if_paused()

            # Verificar skip
            if self.keyboard.should_skip():
                self.tracker.mark(track.track_id, "skip")
                self.queue.task_done()
                continue

            # Procesar canción
            attempt = 0
            success = False
            last_error = ""

            while attempt < self.cfg.MAX_RETRIES and not success:
                if self.keyboard.should_quit():
                    break

                attempt += 1

                try:
                    # 1. Buscar
                    search_result = self.searcher.search(track)

                    # 2. Descargar
                    task_id = self.tracker.add_download_task(track.title)
                    self.tracker.active_downloads.add_row(f"{track.artist} - {track.title}", "Downloading...")

                    # Obtener subcarpeta si existe (inyectada por Builder)
                    subfolder = getattr(track, "playlist_subfolder", "")

                    try:
                        result = self.downloader.download(search_result, track, lambda: self.keyboard.should_quit(), subfolder=subfolder)
                    finally:
                        self.tracker.remove_task(task_id)

                    if not result.success:
                        raise RecoverableError(result.error or "Unknown download error")

                    # Éxito
                    status = "skip" if result.skipped else "ok"
                    self.tracker.mark(track.track_id, status, result.bytes)
                    success = True

                except FatalError as e:
                    last_error = str(e)
                    self.log.debug(f"Error fatal: {e}")
                    break  # No reintentar errores fatales

                except RecoverableError as e:
                    last_error = str(e)
                    if attempt < self.cfg.MAX_RETRIES:
                        self.log.debug(f"Reintento {attempt}/{self.cfg.MAX_RETRIES}: {e}")
                        time.sleep(2 * attempt)  # Backoff exponencial

                except Exception as e:
                    last_error = str(e)
                    self.log.debug(f"Error inesperado: {traceback.format_exc()}")
                    break

            if not success and not self.keyboard.should_quit():
                self.tracker.mark(track.track_id, "err")
                self.failed_tracks.append((track, last_error))

            self.queue.task_done()

            # Guardar checkpoint periódicamente
            processed = self.tracker.ok_count + self.tracker.err_count + self.tracker.skip_count
            if processed % 5 == 0:
                self.tracker.save()

    def _save_failed(self):
        """Guarda canciones fallidas"""
        if not self.failed_tracks:
            return

        # TXT legible
        with open(self.cfg.ERROR_FILE, "w", encoding="utf-8") as f:
            f.write(f"CANCIONES FALLIDAS - {datetime.now()}\n")
            f.write("=" * 60 + "\n\n")
            for track, error in self.failed_tracks:
                f.write(f"• {track.artist} - {track.title}\n")
                f.write(f"  Error: {error}\n\n")

        # CSV para reintentar
        with open(self.cfg.ERROR_CSV, "w", encoding="utf-8", newline="") as f:
            if self.failed_tracks:
                sample = self.failed_tracks[0][0].raw_data
                fieldnames = list(sample.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for track, _ in self.failed_tracks:
                    writer.writerow(track.raw_data)

    def _print_summary(self):
        """Imprime resumen final con Rich"""
        elapsed = time.time() - self.tracker.start_time

        console.print("\n")
        console.print(
            Panel(
                self.tracker.get_stats_table(),
                title=f"Final Summary - {format_time(elapsed)} - {format_size(self.tracker.bytes_total)}",
                border_style="green",
            )
        )

        if self.failed_tracks:
            console.print(f"[yellow]Failed tracks saved to: {self.cfg.ERROR_FILE}[/yellow]")

        # Guardar historial
        session_data = {
            "date": datetime.now().isoformat(),
            "success": self.tracker.ok_count,
            "skipped": self.tracker.skip_count,
            "failed": self.tracker.err_count,
            "duration_sec": int(elapsed),
            "bytes": self.tracker.bytes_total,
            "mode": self.cfg.MODE,
        }
        if self.cfg.SAVE_HISTORY:
            save_history(self.cfg.HISTORY_FILE, session_data)

        # Exportar playlist M3U
        if self.cfg.GENERATE_M3U and self.tracker.ok_count > 0:
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
            except:
                pass

        print("=" * 60)
