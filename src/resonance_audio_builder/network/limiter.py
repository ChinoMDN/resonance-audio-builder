import random
import threading
import time


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
            # Jitter de +/- 10%
            jitter = random.uniform(0.9, 1.1)  # nosec B311
            self.current_delay = min(self.max_delay, self.current_delay * 1.5 * jitter)

    def get_delay(self) -> float:
        return self.current_delay


class CircuitBreaker:
    """Detiene todas las operaciones si detecta demasiados errores (429)"""

    def __init__(self, threshold: int = 3, cooldown: int = 300):
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.failures = 0
        self.threshold = threshold
        self.cooldown = cooldown
        self.last_failure_time = 0
        self.lock = threading.Lock()

    def record_failure(self):
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.threshold:
                self.state = "OPEN"

    def record_success(self):
        with self.lock:
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0

    def check(self):
        """Lanza excepción si el circuito está abierto"""
        if self.state == "OPEN":
            elapsed = time.time() - self.last_failure_time
            if elapsed > self.cooldown:
                self.state = "HALF_OPEN"
            else:
                remaining = int(self.cooldown - elapsed)
                raise Exception(f"Circuit Breaker OPEN. Pausing for {remaining}s due to Rate Limits.")
