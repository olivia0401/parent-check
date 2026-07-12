"""
Sliding-window rate limiter backed by Redis, with an in-memory fallback.

The old limiter kept a per-process dict of timestamps. That only works for a
single gunicorn worker: with several workers or ECS tasks behind a load
balancer, each process sees only its own slice of traffic, so the real limit is
`workers * RATE_LIMIT`. This enforces the limit across all workers via a Redis
sorted set, and degrades to the old per-process behaviour if Redis is
unreachable (local dev / CI), so the app never 500s just because Redis is down.
"""
import os
import time
from collections import deque
from threading import Lock

try:
    import redis
except ImportError:  # redis not installed (e.g. minimal CI) -> memory fallback
    redis = None

# Atomic sliding window run inside Redis: drop hits older than the window, count
# what's left, and if under the limit add the new hit. Returns 1 allowed / 0 not.
# Doing it in one Lua call avoids a check-then-act race between workers.
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('PEXPIRE', key, window * 1000)
    return 1
end
return 0
"""


class RateLimiter:
    """`limit` requests per `window` seconds, keyed by an arbitrary string (IP)."""

    def __init__(self, limit, window, redis_url=None):
        self.limit = limit
        self.window = window
        self._redis = None
        self._script = None
        self._fallback = {}  # key -> deque[timestamps]
        self._lock = Lock()

        url = redis_url or os.environ.get("REDIS_URL")
        if url and redis is not None:
            try:
                client = redis.Redis.from_url(url, socket_connect_timeout=0.5)
                client.ping()
                self._redis = client
                self._script = client.register_script(_SLIDING_WINDOW_LUA)
            except Exception:
                self._redis = None  # unreachable at startup -> use memory

    @property
    def backend(self):
        return "redis" if self._redis is not None else "memory"

    def allow(self, key):
        """Return True if this key may proceed, False if it is rate-limited."""
        now = time.time()
        if self._redis is not None:
            try:
                allowed = self._script(
                    keys=[f"rl:{key}"], args=[now, self.window, self.limit]
                )
                return bool(allowed)
            except Exception:
                # Redis died mid-request: degrade instead of returning a 500.
                self._redis = None
        return self._allow_memory(key, now)

    def _allow_memory(self, key, now):
        with self._lock:
            if len(self._fallback) > 5000:  # bound memory
                self._fallback.clear()
            hits = self._fallback.setdefault(key, deque())
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
