from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, max_per_minute: int = 20):
        self._max = max_per_minute
        self._tokens = float(max_per_minute)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            while self._tokens < 1.0:
                wait = (1.0 - self._tokens) / (self._max / 60.0)
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._max), self._tokens + elapsed * (self._max / 60.0))
        self._last_refill = now

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens
