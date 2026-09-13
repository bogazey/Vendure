"""Minimal in-memory sliding-window rate limiter — copied from Loady's
`rate_limit_service.py` verbatim (same reasoning: this process runs single-
instance in dev/V1; swap for a Redis-backed limiter before scaling out
horizontally).
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str, max_events: int, window_seconds: float) -> bool:
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


login_limiter = RateLimiter()
signup_limiter = RateLimiter()
password_reset_limiter = RateLimiter()
oauth_token_limiter = RateLimiter()
# Grand Admin mutations (mission 4, phase 10): bounds the blast radius of a
# compromised/leaked admin session or a runaway script — generous enough
# never to block normal interactive admin use, keyed per-admin so one
# admin's activity never throttles another's.
admin_mutation_limiter = RateLimiter()
# Mission 6 (Phase 10): a legitimate provider will retry a webhook delivery
# several times if Platform Core is briefly unavailable - this must not be
# tripped by normal retry behavior, so it is deliberately far more generous
# than the interactive limiters above and keyed per-provider, not per-event.
billing_webhook_limiter = RateLimiter()
