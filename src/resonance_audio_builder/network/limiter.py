import threading
import time
import random

class RateLimiter:
    """Rate limiter adaptativo"""

    def __init__(self, min_delay: float = 0.5, max_delay: float = 2.0):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.current_delay = min_delay
        self.consecutive_errors = 0
        self.lock = threading.Lock()

    def wait(self):
        """Espera segun el delay actual"""
        time.sleep(self.current_delay + random.uniform(0, 0.5))

    def success(self):
        """Registra exito - reduce delay"""
        with self.lock:
            self.consecutive_errors = 0
            self.current_delay = max(self.min_delay, self.current_delay * 0.9)

    def error(self):
        """Registra error - aumenta delay"""
        with self.lock:
            self.consecutive_errors += 1
            self.current_delay = min(self.max_delay, self.current_delay * 1.5)

    def get_delay(self) -> float:
        return self.current_delay
