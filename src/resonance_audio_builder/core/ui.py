import threading
from collections import deque
from dataclasses import dataclass
from typing import Dict, Optional

from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from resonance_audio_builder.core.config import Config

console = Console()


@dataclass
class UITask:
    """Representa el estado de una tarea activa en la UI"""

    artist: str
    title: str
    status: str = "Starting"
    total_bytes: int = 100
    completed_bytes: int = 0


def print_header():
    """Display the application header banner."""
    console.print(
        Panel(
            Align.center("[bold white]Resonance Music Downloader v8.1[/bold white]"),
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def format_time(seconds: float) -> str:
    """Format seconds into a human-readable time string."""
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def format_size(size_bytes: int) -> str:
    """Format byte count into a human-readable size string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.2f} TB"


class RichUI:
    """Gestor de Interfaz de Usuario (Rich) - Dashboard Layout"""

    def __init__(self, config: Config):
        self.cfg = config
        self.lock = threading.RLock()

        # Overall Progress
        self.overall_progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )

        # Active Downloads Progress (Internal manager for bars, not shown directly)
        self.job_progress = Progress(
            TextColumn("{task.fields[status]}"),
            BarColumn(bar_width=20),
            DownloadColumn(),
            TransferSpeedColumn(),
        )

        self.live: Optional[Live] = None
        self.main_task: Optional[TaskID] = None
        self.layout: Optional[Layout] = None

        # Internal State tracking for Table (Shadow State)
        self.active_tasks: Dict[TaskID, UITask] = {}

        self.log_buffer: deque[str] = deque(maxlen=20)
        self.log_text = Text("")

    def start(self, total: int):
        """Inicializa y arranca el dashboard Live"""
        with self.lock:
            if self.live:
                return

            self.main_task = self.overall_progress.add_task("[cyan]Batch Progress", total=total)

            self.layout = Layout()
            self.layout.split(
                Layout(name="header", size=3),
                Layout(name="main"),
                Layout(name="footer", size=10),
            )

            self.layout["main"].split_row(Layout(name="active", ratio=2), Layout(name="stats", ratio=1))

            # Initial render
            self.make_layout()

            # Pass get_renderable=self.make_layout to auto-refresh
            self.live = Live(get_renderable=self.make_layout, refresh_per_second=4, console=console, screen=True)
            self.live.start()

    def make_layout(self):
        """Build and return the Rich layout for the dashboard."""
        try:
            # Active Table
            table = Table(expand=True, border_style="dim", box=None)
            table.add_column("Song", style="bold white", ratio=3)
            table.add_column("Status", style="cyan", ratio=2)
            table.add_column("Progress", ratio=2)

            with self.lock:
                tasks_snapshot = list(self.active_tasks.items())

            # Generate rows from active tasks
            for _, info in tasks_snapshot:
                # Usar shadow-state (UITask) para evitar acceso a _tasks (privado de Rich)
                status = info.status
                progress_bar = ProgressBar(total=info.total_bytes, completed=info.completed_bytes, width=20)

                table.add_row(f"{info.artist} - {info.title}", status, progress_bar)

            if not tasks_snapshot:
                table.add_row("[dim]Waiting for tasks...[/dim]", "", "")

            if self.layout:
                self.layout["header"].update(Panel(self.overall_progress, border_style="cyan"))
                self.layout["active"].update(Panel(table, title="Active Downloads", border_style="blue"))

            # Stats / Logs
            if self.cfg.DEBUG_MODE:
                self.layout["footer"].update(Panel(self.log_text, title="Log", border_style="dim"))
            else:
                self.layout["footer"].visible = False

            # Side stats
            with self.lock:
                pending_count = len(self.active_tasks)

            stats_txt = Text.from_markup(
                f"""
[bold]Configuration[/bold]
Mode: {self.cfg.MODE}
Workers: {self.cfg.MAX_WORKERS}
Proxies: {'Enabled' if self.cfg.USE_PROXIES else 'Disabled'}

[bold]Session[/bold]
Active Workers: {pending_count}
    """
            )
            self.layout["stats"].update(Panel(stats_txt, title="Information", border_style="magenta"))

            return self.layout
        except Exception as e:
            with open("debug_ui.txt", "a", encoding="utf-8") as f:
                f.write(f"CRASH in make_layout: {e}\n")
                import traceback

                f.write(traceback.format_exc())
            return Layout()  # Return empty layout on crash

    def stop(self):
        """Detiene el dashboard Live de forma segura"""
        with self.lock:
            if self.live:
                self.live.stop()
                self.live = None

    def update_main_progress(self, advance: int = 1):
        """Advance the overall progress bar."""
        if self.main_task is not None:
            self.overall_progress.update(self.main_task, advance=advance)
            # Live auto-refreshes via make_layout callback, no need manual update

    def add_download_task(self, artist: str, title: str, total_bytes: int = 100) -> TaskID:
        """Register a new download task in the UI."""
        tid = self.job_progress.add_task("download", total=total_bytes, status="Starting")
        with self.lock:
            self.active_tasks[tid] = UITask(artist=artist, title=title, total_bytes=total_bytes)
        return tid

    def update_task_status(self, task_id: TaskID, status: str):
        """Update the display status of a download task."""
        # Actualizar shadow-state
        with self.lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id].status = status

        # job_progress es thread safe
        self.job_progress.update(task_id, status=status)

    def update_download(self, task_id: TaskID, advance: int):
        """Advance the download progress of a task."""
        # Actualizar shadow-state
        with self.lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id].completed_bytes += advance

        self.job_progress.update(task_id, advance=advance)

    def remove_task(self, task_id: TaskID):
        """Remove a completed or failed task from the UI."""
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

        # Don't remove from job_progress immediately to avoid issues?
        # Actually it's cleaner to remove.
        try:
            self.job_progress.remove_task(task_id)
        except Exception:
            pass

    def add_log(self, msg: str):
        """Append a log message to the live log buffer."""
        # Called from Logger. Thread safe usually, but deque append is atomic.
        # But log_text generation might flicker?
        self.log_buffer.append(msg)
        clean_text = "\n".join(list(self.log_buffer)[-8:])
        self.log_text.plain = clean_text

    def show_summary(self, stats: dict):
        """Display the final session summary table."""
        t = Table(title="Session Summary")
        t.add_column("Metric", style="cyan")
        t.add_column("Value", style="magenta")

        t.add_row("Successful", str(stats.get("ok", 0)))
        t.add_row("Skipped", str(stats.get("skip", 0)))
        t.add_row("Failed", str(stats.get("error", 0)))
        t.add_row("Total Data", f"{stats.get('bytes', 0) / (1024 * 1024):.2f} MB")

        console.print(t)
