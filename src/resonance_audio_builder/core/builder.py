import asyncio
import csv
import glob
import os
import shutil
import tempfile
import traceback
from pathlib import Path
from typing import List, Optional

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from resonance_audio_builder.audio.metadata import TrackMetadata
from resonance_audio_builder.core.config import Config, QualityMode
from resonance_audio_builder.core.logger import Logger
from resonance_audio_builder.core.manager import DownloadManager
from resonance_audio_builder.core.state import ProgressDB
from resonance_audio_builder.core.ui import console, print_header
from resonance_audio_builder.network.cache import CacheManager
from resonance_audio_builder.network.limiter import RateLimiter
from resonance_audio_builder.network.utils import validate_cookies_file


class App:
    def __init__(self):
        self.cfg = Config.load()  # Carga desde config.json si existe
        self.log = Logger(self.cfg.DEBUG_MODE)
        self.db = ProgressDB(self.cfg)

        # Init SQLite Cache (replaces old JSON cache)
        try:
            self.cache = CacheManager("cache.db")
        except Exception as e:
            self.log.error(f"Failed to init cache: {e}")
            self.cache = None
        self.rate_limiter = RateLimiter(self.cfg.RATE_LIMIT_MIN, self.cfg.RATE_LIMIT_MAX)

    def _check_dependencies(self) -> bool:
        if not shutil.which("ffmpeg"):
            print("\n[ERROR] FFmpeg no está instalado.")
            print("        Descárgalo de: https://ffmpeg.org/download.html")
            return False
        return True

    def _check_dependencies_silent(self) -> bool:
        return validate_cookies_file(self.cfg.COOKIES_FILE)

    def _show_status(self):
        cookies_status = (
            "[bold green]OK[/bold green]" if self._check_dependencies_silent() else "[yellow]Missing[/yellow]"
        )

        # Stats
        cache_count = self.cache.count() if self.cache else 0

        # Get stats from DB
        stats = self.db.get_stats()
        progress_count = stats.get("ok", 0) + stats.get("skip", 0) + stats.get("error", 0)

        # Grid layout
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)

        # Left Panel: System
        deno_ok = shutil.which("deno") or os.path.exists(Path.home() / ".deno" / "bin" / "deno.exe")
        sys_info = f"""[bold]FFmpeg:[/bold]    [green]Installed[/green]
[bold]Deno:[/bold]      {'[green]Installed[/green]' if deno_ok else '[dim]Optional[/dim]'}
[bold]Cookies:[/bold]   {cookies_status}"""

        # Right Panel: Data
        data_info = f"""[bold]Cache:[/bold]     {cache_count} entries (SQLite)
[bold]History:[/bold]   {progress_count} songs
[bold]Quality:[/bold]   {self.cfg.MODE}"""

        grid.add_row(
            Panel(sys_info, title="System Status", border_style="blue"),
            Panel(data_info, title="Data Metrics", border_style="magenta"),
        )

        console.print(grid)

    def _select_csv(self) -> List[str]:
        console.clear()
        print_header()

        # Ensure input folder exists
        inp_dir = Path(self.cfg.INPUT_FOLDER)
        inp_dir.mkdir(exist_ok=True)

        # Glob uses OS separators logic? glob.glob accepts paths.
        pattern = str(inp_dir / "*.csv")
        csvs = [c for c in glob.glob(pattern) if "fallidas" not in c.lower()]

        if not csvs:
            console.print(
                Panel(
                    f"[yellow]No CSV files found in '{self.cfg.INPUT_FOLDER}/' directory.[/yellow]\n\n"
                    f"Please move your exported playlists there.",
                    title="Warning",
                    border_style="yellow",
                )
            )
            return []

        # Single file case
        if len(csvs) == 1:
            console.print(Panel(f"[bold green]Selected file:[/bold green] {csvs[0]}", border_style="green"))
            return [csvs[0]]

        # Multiple files case
        table = Table(title="Select CSV File", show_header=True, header_style="bold magenta", expand=True)
        table.add_column("#", style="dim", width=4)
        table.add_column("Filename", style="bold cyan")
        table.add_column("Size", justify="right")

        for i, f in enumerate(csvs):
            size_mb = os.path.getsize(f) / 1024
            table.add_row(str(i + 1), f, f"{size_mb:.1f} KB")

        table.add_row("A", "[bold green]ALL FILES[/bold green]", "")

        console.print(table)

        choices = [str(i + 1) for i in range(len(csvs))] + ["A"]
        sel = Prompt.ask("Choose a file (or 'A' for All)", choices=choices, default="1")

        if sel.upper() == "A":
            return csvs

        return [csvs[int(sel) - 1]]

    def _select_quality(self):
        console.clear()
        print_header()

        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(ratio=1)
        grid.add_column(ratio=3)

        grid.add_row("[bold cyan]1.[/bold cyan] High Quality", "320kbps MP3 (Best for PC/Hi-Fi)")
        grid.add_row("[bold cyan]2.[/bold cyan] Mobile", "96kbps MP3 (Save space)")
        grid.add_row("[bold cyan]3.[/bold cyan] Both", "High Quality + Mobile versions")

        console.print(Panel(grid, title="Select Quality", border_style="cyan"))

        sel = Prompt.ask("Option", choices=["1", "2", "3"], default="3")

        if sel == "1":
            self.cfg.MODE = QualityMode.HQ_ONLY
            console.print("[dim]Selected: High Quality only[/dim]")
        elif sel == "2":
            self.cfg.MODE = QualityMode.MOBILE_ONLY
            console.print("[dim]Selected: Mobile only[/dim]")
        elif sel == "3":
            self.cfg.MODE = QualityMode.BOTH
            console.print("[dim]Selected: Both versions[/dim]")

    def _read_csv(self, filepath: str) -> List[dict]:
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]

        for enc in encodings:
            try:
                with open(filepath, "r", encoding=enc) as f:
                    sample = f.read(1024)
                    f.seek(0)
                    if "\0" in sample:
                        continue

                    reader = csv.DictReader(f)
                    rows = list(reader)
                    if len(rows) > 0 and reader.fieldnames:
                        self.log.info(f"[i] Codificación: {enc}")
                        return rows
            except Exception:
                continue

        print(f"[!] Error leyendo CSV: {filepath}")
        return []

    def _collect_tracks(self, csv_files: List[str]) -> List[TrackMetadata]:
        """Lee y agrupa canciones de múltiples CSVs"""
        all_tracks = []
        for csv_file in csv_files:
            rows = self._read_csv(csv_file)
            playlist_name = Path(csv_file).stem
            if rows:
                for row in rows:
                    t = TrackMetadata.from_csv_row(row)
                    setattr(t, "playlist_subfolder", playlist_name)
                    all_tracks.append(t)
        return all_tracks

    def _deduplicate_tracks(self, tracks: List[TrackMetadata]) -> List[TrackMetadata]:
        """Elimina canciones duplicadas por ID"""
        unique = {}
        for t in tracks:
            if t.track_id not in unique:
                unique[t.track_id] = t
        return list(unique.values())

    def _get_selected_csvs(self, csv_files: Optional[List[str]]) -> List[str]:
        """Obtiene la lista de CSVs a procesar"""
        if csv_files is not None:
            return csv_files

        console.clear()
        print_header()
        return self._select_csv()

    def _start_download(self, csv_files: List[str] = None, ask_quality: bool = True):
        """Inicia descarga de lista de CSVs modularmente"""
        csv_files = self._get_selected_csvs(csv_files)
        if not csv_files:
            console.print("\n[bold cyan]Presiona ENTER para continuar...[/bold cyan]")
            return

        if ask_quality:
            self._select_quality()

        all_tracks = self._collect_tracks(csv_files)
        if not all_tracks:
            print("\n[!] No tracks found in selected files.")
            if ask_quality:
                input("\nENTER para continuar...")
            return

        tracks = self._deduplicate_tracks(all_tracks)
        print(f"\n[i] {len(tracks)} canciones únicas detectadas en total")

        try:
            manager = DownloadManager(self.cfg, self.cache)
            asyncio.run(manager.run(tracks))
        except Exception:
            with open("crash.log", "w", encoding="utf-8") as f:
                f.write(traceback.format_exc())
            console.print("\n[bold red][!] Error crítico guardado en crash.log[/bold red]")

        console.input("\n[bold cyan]Presiona ENTER para continuar...[/bold cyan]")

    def _retry_failed(self):
        """Reintenta descargar canciones fallidas"""
        console.clear()
        print_header()

        if not os.path.exists(self.cfg.ERROR_CSV):
            console.print("\n[yellow][!] No hay archivo de canciones fallidas.[/yellow]")
            console.print(f"    [dim]({self.cfg.ERROR_CSV} no existe)[/dim]")
            console.input("\n[bold cyan]Presiona ENTER para volver...[/bold cyan]")
            return

        rows = self._read_csv(self.cfg.ERROR_CSV)
        if not rows:
            console.print("\n[yellow][!] El archivo de fallidas esta vacio.[/yellow]")
            console.input("\n[bold cyan]Presiona ENTER para volver...[/bold cyan]")
            return

        tracks = [TrackMetadata.from_csv_row(row) for row in rows]

        # Eliminar de procesadas para que se reintenten
        # pass

        # Eliminar duplicados
        unique = {}
        for t in tracks:
            if t.track_id not in unique:
                unique[t.track_id] = t

        tracks = list(unique.values())

        print(f"\n[i] {len(tracks)} canciones fallidas a reintentar")

        self._select_quality()

        # Ejecutar descarga
        manager = DownloadManager(self.cfg, self.cache)
        asyncio.run(manager.run(tracks))

        input("\nENTER para continuar...")

    def _perform_clear(self, sel: str) -> List[str]:
        """Ejecuta la limpieza solicitada"""
        deleted = []
        if sel in ["1", "3"]:
            self._clear_cache_data()
            deleted.append("Cache (SQLite)")

        if sel in ["2", "3"]:
            self.db.clear()
            deleted.append("Progress (DB)")

        if sel == "3":
            self._clear_temp_files()
            deleted.append("Temp Files")

        return deleted

    def _clear_cache_data(self):
        if self.cache:
            self.cache.clear()
        for f in ["cache.db", self.cfg.CACHE_FILE]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def _clear_temp_files(self):
        temp_dir = Path(tempfile.gettempdir())
        for f in temp_dir.glob("ytraw_*"):
            try:
                os.remove(f)
            except Exception:
                pass

    def _clear_cache(self):
        """Menú de limpieza modular"""
        console.clear()
        print_header()
        table = Table(title="Clear Data", show_header=False, box=None)
        rows = [("[1]", "Clear Search Cache"), ("[2]", "Clear Progress"), ("[3]", "Clear All"), ("[0]", "Cancel")]
        for r in rows:
            table.add_row(r[0], r[1])

        console.print(Panel(table, border_style="red"))
        sel = Prompt.ask("Option", choices=["0", "1", "2", "3"], default="0")
        if sel == "0":
            return

        deleted = self._perform_clear(sel)
        if deleted:
            console.print(f"[green]Deleted: {', '.join(deleted)}[/green]")
        Prompt.ask("\nPress ENTER to continue")

        if deleted:
            console.print(f"[green]Deleted: {', '.join(deleted)}[/green]")
        else:
            console.print("[dim]Nothing to delete.[/dim]")

        Prompt.ask("\nPress ENTER to continue")

    def _notify_end(self):
        """Sonido de notificacion"""
        try:
            if os.name == "nt":
                import winsound

                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                print("\a")
        except Exception:
            pass

    def watch_mode(self, folder: str):
        """Inicia el modo Watchdog"""
        from resonance_audio_builder.watch.observer import start_observer

        if not os.path.exists(folder):
            print(f"[!] Folder not found: {folder}")
            return

        console.clear()
        print_header()

        # Preguntar calidad UNA sola vez al inicio
        self._select_quality()

        console.print(f"[green]Quality set to: {self.cfg.MODE}. Monitoring for new CSVs...[/green]")

        start_observer(folder, self)

    def run(self):
        # Chequear argumentos CLI manualmente (simple)
        import sys

        if len(sys.argv) > 1:
            if sys.argv[1] == "--watch":
                # Default to INPUT_FOLDER (Playlists) if no arg provided
                default_watch = self.cfg.INPUT_FOLDER
                folder = sys.argv[2] if len(sys.argv) > 2 else default_watch

                # Ensure it exists
                Path(folder).mkdir(exist_ok=True)

                self.watch_mode(folder)
                return

        if not self._check_dependencies():
            input("\nPress ENTER to exit...")
            return

        while True:
            console.clear()
            print_header()

            self._show_status()

            # Menu Principal con Grid
            menu_table = Table(show_header=False, box=None, padding=(0, 2))
            menu_table.add_row("[bold cyan]1.[/bold cyan] Start download from CSV(s)", style="bold")
            menu_table.add_row("[bold cyan]2.[/bold cyan] Retry failed songs")
            menu_table.add_row("[bold cyan]3.[/bold cyan] Clear cache/progress")
            menu_table.add_row("[bold red]4.[/bold red] Exit")

            console.print(Panel(menu_table, title="Main Menu", border_style="blue"))

            sel = Prompt.ask("Option", choices=["1", "2", "3", "4"])

            if sel == "1":
                self._start_download()  # Interactivo
                console.input("\n[bold cyan]Presiona ENTER para continuar...[/bold cyan]")
                self._notify_end()
            elif sel == "2":
                self._retry_failed()
                self._notify_end()
            elif sel == "3":
                self._clear_cache()
            elif sel == "4":
                console.print("\n[magenta]Goodbye![/magenta]")
                break
