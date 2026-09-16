"""A small in-process rate limiter.

Deliberately not Redis-backed: the target deployment is a single free-tier
container, and an external dependency would be the most fragile part of the
system. The trade-off is explicit - limits are per-process, so they are only
correct while the service runs one replica.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class SlidingWindowRateLimiter:
    """Allows ``limit`` requests per ``window_seconds`` for each key."""

    def __init__(self, limit: int, window_seconds: int, *, max_keys: int = 10_000) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit for ``key``.

        Returns ``(allowed, retry_after_seconds)``.
        """
        now = time.monotonic()
        cutoff = now - self._window

        with self._lock:
            if len(self._hits) > self._max_keys:
                # Bound memory against a flood of distinct client addresses.
                self._evict(cutoff)

            hits = self._hits[key]

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self._limit:
                return False, max(1, int(hits[0] + self._window - now) + 1)

            hits.append(now)
            return True, 0

    def _evict(self, cutoff: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._hits[key]
