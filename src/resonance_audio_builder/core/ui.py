import os
import threading
from collections import deque
from typing import Dict

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


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")  # nosec B605


def print_header():
    console.print(
        Panel(
            Align.center("[bold white]Resonance Music Downloader v8.1[/bold white]"),
            border_style="cyan",
            padding=(1, 2),
            expand=True,
        )
    )


def format_time(seconds: float) -> str:
    if seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def format_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
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

        self.live = None
        self.main_task = None

        # Internal State tracking for Table
        self.active_tasks: Dict[TaskID, dict] = {}

        self.log_buffer = deque(maxlen=20)
        self.log_text = Text("")

    def start(self, total: int):
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
        try:
            # Active Table
            table = Table(expand=True, border_style="dim", box=None)
            table.add_column("Song", style="bold white", ratio=3)
            table.add_column("Status", style="cyan", ratio=2)
            table.add_column("Progress", ratio=2)

            with self.lock:
                tasks_snapshot = list(self.active_tasks.items())

            # Generate rows from active tasks
            for task_id, info in tasks_snapshot:
                status = "Unknown"
                bar = Text("Initializing...")

                # job_progress access (Thread safe-ish)
                if task_id in self.job_progress._tasks:
                    t = self.job_progress._tasks[task_id]
                    status = str(t.fields.get("status", ""))
                    # bar = self.job_progress.get_renderable(task_id) # ERROR

                    # Manual Bar
                    total = t.total or 100
                    completed = t.completed
                    bar = ProgressBar(total=total, completed=completed, width=20)

                table.add_row(f"{info['artist']} - {info['title']}", status, bar)

            if not tasks_snapshot:
                table.add_row("[dim]Waiting for tasks...[/dim]", "", "")

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
            with open("debug_ui.txt", "a") as f:
                f.write(f"CRASH in make_layout: {e}\n")
                import traceback

                f.write(traceback.format_exc())
            return Layout()  # Return empty layout on crash

    def stop(self):
        if self.live:
            self.live.stop()

    def update_main_progress(self, advance: int = 1):
        if self.main_task is not None:
            self.overall_progress.update(self.main_task, advance=advance)
            # Live auto-refreshes via make_layout callback, no need manual update

    def add_download_task(self, artist: str, title: str, total_bytes: int = 100) -> TaskID:
        tid = self.job_progress.add_task("download", total=total_bytes, status="Starting")
        with self.lock:
            self.active_tasks[tid] = {"artist": artist, "title": title}
        return tid

    def update_task_status(self, task_id: TaskID, status: str):
        # job_progress is thread safe
        if task_id in self.job_progress._tasks:
            self.job_progress.update(task_id, status=status)

    def update_download(self, task_id: TaskID, advance: int):
        if task_id in self.job_progress._tasks:
            self.job_progress.update(task_id, advance=advance)

    def remove_task(self, task_id: TaskID):
        with self.lock:
            if task_id in self.active_tasks:
                del self.active_tasks[task_id]

        # Don't remove from job_progress immediately to avoid issues?
        # Actually it's cleaner to remove.
        try:
            if task_id in self.job_progress._tasks:
                self.job_progress.remove_task(task_id)
        except Exception:
            pass

    def add_log(self, msg: str):
        # Called from Logger. Thread safe usually, but deque append is atomic.
        # But log_text generation might flicker?
        self.log_buffer.append(msg)
        clean_text = "\n".join(list(self.log_buffer)[-8:])
        self.log_text.plain = clean_text

    def show_summary(self, stats: dict):
        t = Table(title="Session Summary")
        t.add_column("Metric", style="cyan")
        t.add_column("Value", style="magenta")

        t.add_row("Successful", str(stats.get("ok", 0)))
        t.add_row("Skipped", str(stats.get("skip", 0)))
        t.add_row("Failed", str(stats.get("error", 0)))
        t.add_row("Total Data", f"{stats.get('bytes', 0) / (1024 * 1024):.2f} MB")

        console.print(t)
