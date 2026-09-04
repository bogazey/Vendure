"""Minimal in-memory rate limiter for auth endpoints.

Deliberately not Redis-backed - this app runs as a single process locally
and the limiter's whole job is to blunt brute-force/credential-stuffing
attempts, not provide distributed guarantees. Swap for a Redis-backed
limiter (e.g. behind multiple workers) before scaling out horizontally.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, max_events: int, window_seconds: float) -> bool:
        """Sliding-window check: True if `key` has made fewer than
        `max_events` calls in the trailing `window_seconds`. Records this
        call as a hit regardless of the outcome (failed attempts still
        count, which is what you want for brute-force protection)."""
        now = time.monotonic()
        with self._lock:
            events = self._hits[key]
            cutoff = now - window_seconds
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= max_events:
                return False
            events.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


# Separate limiters per concern so a burst on one endpoint doesn't consume
# another's budget.
login_limiter = RateLimiter()
signup_limiter = RateLimiter()
password_reset_limiter = RateLimiter()
