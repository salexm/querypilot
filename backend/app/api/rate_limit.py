"""Limits on /query, which spends real money on every call.

Counters live in memory, which suits a single instance. They reset on restart,
so the provider's spend limit stays the hard stop.
"""

import math
import time
from collections import deque
from collections.abc import Callable
from functools import lru_cache
from threading import Lock
from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings, get_settings

SECONDS_PER_MINUTE = 60
SECONDS_PER_DAY = 86_400
MAX_TRACKED_KEYS = 10_000


class RateLimitExceededError(Exception):
    def __init__(self, code: str, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _expire(self, hits: deque[float], now: float) -> None:
        while hits and hits[0] <= now - self._window:
            hits.popleft()

    def _forget_idle_keys(self, now: float) -> None:
        """Bound memory, because every new IP address adds a key."""
        for key, hits in list(self._hits.items()):
            self._expire(hits, now)
            if not hits:
                del self._hits[key]

    def wait_seconds(self, key: str) -> int:
        """Record a hit and return 0, or return the wait if the limit is reached."""
        with self._lock:
            now = self._clock()
            if len(self._hits) >= MAX_TRACKED_KEYS:
                self._forget_idle_keys(now)
            hits = self._hits.setdefault(key, deque())
            self._expire(hits, now)
            if len(hits) >= self._limit:
                return max(1, math.ceil(hits[0] + self._window - now))
            hits.append(now)
            return 0


class QueryLimits:
    def __init__(self, per_minute: int, per_day: int) -> None:
        self._per_ip = SlidingWindowLimiter(per_minute, SECONDS_PER_MINUTE)
        self._whole_site = SlidingWindowLimiter(per_day, SECONDS_PER_DAY)

    def check(self, client_ip: str) -> None:
        # Per-IP runs first, so blocked requests don't use up the daily budget.
        wait = self._per_ip.wait_seconds(client_ip)
        if wait:
            message = f"You're asking quickly. Please try again in {wait} seconds."
            raise RateLimitExceededError("rate_limited", message, wait)
        wait = self._whole_site.wait_seconds("all")
        if wait:
            message = "The demo has reached its daily limit. Please try again tomorrow."
            raise RateLimitExceededError("daily_limit_reached", message, wait)


def client_ip(request: Request, trusted_proxy_hops: int) -> str:
    """Find the visitor's address without trusting anything they can forge.

    Each proxy appends to X-Forwarded-For, so only the entries added by our own
    proxies, counted from the right, are reliable. Anything further left came
    from the client.
    """
    direct = request.client.host if request.client else "unknown"
    if trusted_proxy_hops == 0:
        return direct
    forwarded = request.headers.get("x-forwarded-for", "")
    entries = [entry.strip() for entry in forwarded.split(",") if entry.strip()]
    return entries[-trusted_proxy_hops] if len(entries) >= trusted_proxy_hops else direct


@lru_cache
def get_query_limits() -> QueryLimits:
    settings = get_settings()
    return QueryLimits(settings.rate_limit_per_minute, settings.daily_query_limit)


def enforce_query_limits(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    limits: Annotated[QueryLimits, Depends(get_query_limits)],
) -> None:
    limits.check(client_ip(request, settings.trusted_proxy_hops))
