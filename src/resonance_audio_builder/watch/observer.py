import os
import time
from pathlib import Path

from rich.console import Console
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

console = Console()

import threading


class PlaylistEventHandler(FileSystemEventHandler):
    """Maneja eventos de archivos en el modo Watchdog con Debounce"""

    def __init__(self, app_instance, delay=2.0):
        self.app = app_instance
        self.delay = delay
        self.timers = {}
        self.lock = threading.Lock()

    def on_created(self, event):
        if event.is_directory:
            return
        self._debounce(event.src_path)

    def on_modified(self, event):
        if event.is_directory:
            return
        self._debounce(event.src_path)

    def _debounce(self, filepath):
        filename = os.path.basename(filepath)
        if not (filename.lower().endswith(".csv") and "fallidas" not in filename.lower()):
            return

        with self.lock:
            if filepath in self.timers:
                self.timers[filepath].cancel()

            # Show "Detecting..." log only once or sporadically?
            # Better keep it quiet until processing to avoid spamming terminal on every byte written

            timer = threading.Timer(self.delay, self._process_debounced, [filepath])
            self.timers[filepath] = timer
            timer.start()

    def _process_debounced(self, filepath):
        with self.lock:
            if filepath in self.timers:
                del self.timers[filepath]

        console.print(f"\n[bold green]⚡ New playlist stabilized:[/bold green] {filepath}")

        try:
            # Invocar al App builder para procesar
            # Usamos _start_download pasando la lista explícita y SIN preguntar calidad
            self.app._start_download([filepath], ask_quality=False)
            console.print(f"\n[bold blue]👀 Resume watching...[/bold blue]")
        except Exception as e:
            console.print(f"[bold red]Error processing file:[/bold red] {e}")


def start_observer(path: str, app_instance):
    """Inicia el observador de carpeta"""
    event_handler = PlaylistEventHandler(app_instance)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=False)
    observer.start()

    console.print(
        Panel(
            f"[bold cyan]WATCHDOG MODE ACTIVE[/bold cyan]\n"
            f"Monitoring: [yellow]{os.path.abspath(path)}[/yellow]\n"
            f"Drop any .csv file here to start download.\n"
            f"Press [bold red]Ctrl+C[/bold red] to stop.",
            border_style="cyan",
        )
    )

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]Stopping watchdog...[/yellow]")

    observer.join()


from rich.panel import Panel
