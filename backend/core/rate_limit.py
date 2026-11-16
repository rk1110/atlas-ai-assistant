"""Per-user rate limits (Phase 7), counted in Redis.

Fixed-window counters: one key per user per minute ("rl:<user>:m:<minute number>") and one
per day, each incremented on every request and expiring after its window. INCR is atomic in
Redis, so two simultaneous requests can't both slip under the limit, and every backend
replica shares the same counts (a counter in Python memory would be per process).

Fixed windows allow a burst at a window edge (10 requests at 12:00:59 and 10 more at
12:01:00); a sliding window or token bucket smooths that, at the cost of more bookkeeping.
For "stop a runaway script" and "cap a day's spend", fixed windows are enough.

If Redis is down, requests are allowed (logged): limits protect cost, and a cache outage
shouldn't take the whole app down with it.
"""

import logging
import time
import uuid
from typing import Protocol

from core.auth_config import RateLimits

logger = logging.getLogger(__name__)


class CounterStore(Protocol):
    async def increment(self, key: str, ttl_seconds: int) -> int: ...


class RedisCounters:
    def __init__(self, url: str):
        from redis.asyncio import Redis

        self._redis = Redis.from_url(url, socket_timeout=1)

    async def increment(self, key: str, ttl_seconds: int) -> int:
        # One round trip: INCR, and set the expiry only when the key is new (NX).
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, ttl_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count)


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class RateLimiter:
    def __init__(self, store: CounterStore | None, limits: RateLimits):
        self._store = store
        self._limits = limits

    async def check(self, user_id: uuid.UUID) -> None:
        """Count one request; raise RateLimitExceeded if it goes over a limit."""
        if self._store is None:
            return
        now = int(time.time())
        minute, day = now // 60, now // 86_400
        try:
            per_minute = await self._store.increment(f"rl:{user_id}:m:{minute}", 120)
            per_day = await self._store.increment(f"rl:{user_id}:d:{day}", 2 * 86_400)
        except Exception:
            logger.warning("rate limiter unavailable; allowing the request", exc_info=True)
            return
        if per_minute > self._limits.per_minute:
            raise RateLimitExceeded(
                f"Slow down: at most {self._limits.per_minute} messages a minute.",
                retry_after=60 - now % 60,
            )
        if per_day > self._limits.per_day:
            raise RateLimitExceeded(
                f"Daily limit reached ({self._limits.per_day} messages). It resets at 00:00 UTC.",
                retry_after=86_400 - now % 86_400,
            )
