"""Bounded JPEG frame pipeline. Compatible with the original per-frame browser ACK."""
from collections import deque
import threading
import time


class FrameWindow:
    def __init__(self, max_bytes=2 * 1024 * 1024, timeout=10):
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.pending = deque()
        self.pending_bytes = 0
        self.rtt_ms = None
        self.closed = False
        self.condition = threading.Condition()

    @staticmethod
    def capacity(fps):
        # Keep old low-rate presets conservative; high-rate presets tolerate WAN delay.
        return 1 if fps <= 15 else (4 if fps <= 30 else 8)

    def wait(self, fps, stopped, frame_bytes=0):
        with self.condition:
            while not self.closed and not stopped.is_set():
                now = time.monotonic()
                if self.pending and now - self.pending[0][0] >= self.timeout:
                    raise TimeoutError("Viewer stopped acknowledging frames")
                size_ok = not self.pending or self.pending_bytes + frame_bytes <= self.max_bytes
                if len(self.pending) < self.capacity(fps) and size_ok:
                    return True
                self.condition.wait(0.05)
            return False

    def sent(self, size):
        # Called before sending: a very fast ACK must not race ahead of bookkeeping.
        with self.condition:
            if self.closed:
                return False
            self.pending.append((time.monotonic(), size))
            self.pending_bytes += size
            return True

    def acknowledge(self):
        with self.condition:
            if not self.pending:
                return False
            sent, size = self.pending.popleft()
            self.pending_bytes -= size
            elapsed = (time.monotonic() - sent) * 1000
            self.rtt_ms = elapsed if self.rtt_ms is None else self.rtt_ms * 0.8 + elapsed * 0.2
            self.condition.notify_all()
            return True

    def close(self):
        with self.condition:
            self.closed = True
            self.pending.clear()
            self.pending_bytes = 0
            self.condition.notify_all()
