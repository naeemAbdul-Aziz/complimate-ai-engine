import threading
import time
from typing import Optional


class SimpleCircuitBreaker:
    def __init__(self, fail_threshold: int, reset_seconds: int):
        self.fail_threshold = max(1, fail_threshold)
        self.reset_seconds = max(1, reset_seconds)
        self._lock = threading.Lock()
        self._fail_count = 0
        self._open_until = 0.0

    def record_success(self) -> None:
        with self._lock:
            self._fail_count = 0
            self._open_until = 0.0

    def record_failure(self) -> None:
        with self._lock:
            now = time.time()
            if self._open_until and now < self._open_until:
                return
            self._fail_count += 1
            if self._fail_count >= self.fail_threshold:
                self._open_until = now + self.reset_seconds

    def is_open(self) -> bool:
        with self._lock:
            if not self._open_until:
                return False
            if time.time() >= self._open_until:
                # Cooldown passed; half-open
                self._fail_count = 0
                self._open_until = 0.0
                return False
            return True
