import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Dict, Set

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from .config import Config

console = Console()

class RichProgressTracker:
    def __init__(self, config: Config):
        self.cfg = config
        self.processed: Set[str] = set()
        self.lock = threading.RLock()

        self.ok_count = 0
        self.err_count = 0
        self.skip_count = 0
        self.bytes_total = 0
        self.start_time = 0

        # Rich UI components
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
        )
        self.active_downloads = Table.grid(expand=True)
        self.active_downloads.add_column(style="dim")
        self.active_downloads.add_column(justify="right")

        self.log_buffer = deque(maxlen=8)
        self.log_panel = None

        self.layout = None
        self.live = None
        self.main_task = None
        self.download_tasks: Dict[str, TaskID] = {}

        self._load()

    def _load(self):
        if os.path.exists(self.cfg.CHECKPOINT_FILE):
            try:
                with open(self.cfg.CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.processed = set(data)
            except:
                pass

    def save(self):
        with self.lock:
            try:
                with open(self.cfg.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(self.processed), f)
            except:
                pass

    def reset_stats(self):
        with self.lock:
            self.ok_count = 0
            self.err_count = 0
            self.skip_count = 0
            self.bytes_total = 0
            self.start_time = time.time()

    def reset_all(self):
        """Reset all progress - uses RLock so nested calls work"""
        with self.lock:
            self.processed.clear()
            self.reset_stats()
        # Save outside of lock to avoid potential issues
        self._save_no_lock()

    def _save_no_lock(self):
        """Internal save without acquiring lock"""
        try:
            with open(self.cfg.CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self.processed), f)
        except:
            pass

    def get_stats_string(self) -> str:
        with self.lock:
            return f"OK: {self.ok_count} | Skp: {self.skip_count} | Err: {self.err_count}"

    def start(self, total: int):
        self.start_time = time.time()
        self.main_task = self.progress.add_task("[cyan]Total Progress", total=total)

        # Initial logs
        panels = [
            Panel(self.progress, title="Overall Progress", border_style="cyan"),
            Panel(self.active_downloads, title="Active Downloads", border_style="green"),
        ]

        if self.cfg.DEBUG_MODE:
            self.log_text = Text("\n".join(self.log_buffer) if self.log_buffer else "[dim]Waiting for logs...[/dim]")
            panels.append(Panel(self.log_text, title="Live Logs", border_style="dim", height=10))

        self.layout = Group(*panels)
        self.live = Live(self.layout, refresh_per_second=4, console=console)
        self.live.start()

    def add_log(self, msg: str):
        self.log_buffer.append(msg)

        # Keep buffer small
        if len(self.log_buffer) > 50:
            self.log_buffer = self.log_buffer[-50:]

        if hasattr(self, "log_text"):
            start_idx = max(0, len(self.log_buffer) - 10)
            # Remove rich tags for cleaner log history in UI
            clean_text = "\n".join(self.log_buffer[start_idx:])
            self.log_text.plain = clean_text  # Update Text object in-place

    def stop(self):
        if self.live:
            self.live.stop()

    def add_download_task(self, name: str, total_bytes: int = 100) -> TaskID:
        # Añadir al progress
        task_id = self.progress.add_task(f"[green]Downloading {name[:20]}", total=total_bytes)
        return task_id

    def update_download(self, task_id: TaskID, advance: int):
        self.progress.update(task_id, advance=advance)

    def remove_task(self, task_id: TaskID):
        try:
            self.progress.remove_task(task_id)
        except:
            pass

    def mark(self, track_id: str, status: str, bytes_n: int = 0):
        with self.lock:
            self.processed.add(track_id)
            if status == "ok":
                self.ok_count += 1
            elif status == "skip":
                self.skip_count += 1
            elif status == "error":
                self.err_count += 1
            
            if bytes_n > 0:
                self.bytes_total += bytes_n
                
            self.save()

    def is_done(self, track_id: str) -> bool:
        with self.lock:
            return track_id in self.processed

    def get_stats_table(self):
        """Returns a rich table with final stats"""
        t = Table(title="Session Summary")
        t.add_column("Metric", style="cyan")
        t.add_column("Value", style="magenta")
        
        duration = time.time() - self.start_time
        downloaded_mb = self.bytes_total / (1024 * 1024)
        
        t.add_row("Total Time", f"{duration:.1f}s")
        t.add_row("Downloaded", f"{downloaded_mb:.2f} MB")
        t.add_row("Successful", str(self.ok_count))
        t.add_row("Skipped", str(self.skip_count))
        t.add_row("Failed", str(self.err_count))
        
        return t
