"""In-memory sliding-window rate limiter (per client key)."""

import time
from collections import defaultdict, deque


class RateLimiter:
    """Allow at most ``limit`` calls per ``window`` seconds for each key.

    Single-process only: use a gateway or shared store when running several workers. Once per window, keys whose
    newest call is older than the window are dropped, so memory stays proportional to *recently active* clients.
    """

    def __init__(self, limit: int, window: float = 60.0):
        self.limit = limit
        self.window = window
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self._last_sweep = time.monotonic()

    def allow(self, key: str) -> bool:
        """Record a call for ``key``; return False if it exceeds the limit."""
        now = time.monotonic()
        if now - self._last_sweep > self.window:
            self._sweep(now)
        recent = self.hits[key]
        while recent and now - recent[0] > self.window:
            recent.popleft()
        if len(recent) >= self.limit:
            return False
        recent.append(now)
        return True

    def _sweep(self, now: float) -> None:
        stale = [key for key, times in self.hits.items() if not times or now - times[-1] > self.window]
        for key in stale:
            del self.hits[key]
        self._last_sweep = now
