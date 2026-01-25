import threading
from datetime import datetime

from rich.console import Console

console = Console()


class Logger:
    def __init__(self, debug: bool):
        self._debug = debug
        self._lock = threading.Lock()
        self._tracker = None

    def set_tracker(self, tracker):
        self._tracker = tracker

    def _log_to_file(self, msg_clean):
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg_clean}\n")
        except:
            pass

    def _log(self, level, msg, style):
        # File logging (strip rich markup approximation)
        msg_clean = msg.replace("[", "").replace("]", "")
        self._log_to_file(f"{level.upper()}: {msg_clean}")

        # UI logging
        if hasattr(self, "_tracker") and self._tracker:
            self._tracker.add_log(f"[{style}]{msg}[/{style}]")
        else:
            console.print(f"[{style}]{msg}[/{style}]")

    def info(self, msg):
        with self._lock:
            self._log("info", f"[i] {msg}", "cyan")

    def debug(self, msg):
        if self._debug:
            with self._lock:
                self._log("debug", f"    [DEBUG] {msg}", "dim white")

    def error(self, msg):
        with self._lock:
            self._log("error", f"[X] {msg}", "bold red")

    def success(self, msg):
        with self._lock:
            self._log("success", f"[+] {msg}", "bold green")

    def warning(self, msg):
        with self._lock:
            self._log("warning", f"[!] {msg}", "bold yellow")
