"""Shared Redis throttling with bounded recovery and fail-closed production behavior."""

import logging
import os
import time
import uuid
from collections import deque
from threading import Lock

from runtime_secrets import is_production

try:
    import redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)
_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, ARGV[4])
    redis.call('PEXPIRE', key, window * 1000)
    return 1
end
return 0
"""


class RateLimitUnavailable(RuntimeError):
    pass


class RateLimiter:
    def __init__(self, limit, window, redis_url=None, *, fail_closed=None, retry_interval=5):
        self.limit = limit
        self.window = window
        self._url = redis_url or os.environ.get("REDIS_URL")
        self._fail_closed = is_production() if fail_closed is None else fail_closed
        self._retry_interval = retry_interval
        self._next_retry = 0
        self._redis = None
        self._script = None
        self._fallback = {}
        self._lock = Lock()
        self._connect_lock = Lock()
        if self._url:
            self._connect()

    def _connect(self):
        with self._connect_lock:
            if time.monotonic() < self._next_retry:
                return
            self._next_retry = time.monotonic() + self._retry_interval
            if not self._url or redis is None:
                return
            try:
                client = redis.Redis.from_url(
                    self._url, socket_connect_timeout=0.5, socket_timeout=0.5
                )
                client.ping()
                script = client.register_script(_SLIDING_WINDOW_LUA)
                self._redis, self._script = client, script
            except Exception as exc:
                self._redis = None
                logger.warning("Rate limiter Redis unavailable: %s", type(exc).__name__)

    @property
    def backend(self):
        return (
            "redis" if self._redis is not None else "unavailable" if self._fail_closed else "memory"
        )

    def healthy(self):
        if self._redis is None:
            self._connect()
        if self._redis is not None:
            try:
                return bool(self._redis.ping())
            except Exception:
                self._redis = None
        return not self._fail_closed

    def allow(self, key):
        now = time.time()
        if self._redis is None:
            self._connect()
        if self._redis is not None:
            try:
                return bool(
                    self._script(
                        keys=[f"rl:{key}"],
                        args=[
                            now,
                            self.window,
                            self.limit,
                            uuid.uuid4().hex,
                        ],
                    )
                )
            except Exception as exc:
                self._redis = None
                self._next_retry = time.monotonic() + self._retry_interval
                logger.warning("Rate limiter Redis failed: %s", type(exc).__name__)
        if self._fail_closed:
            raise RateLimitUnavailable("Shared limiter is unavailable")
        return self._allow_memory(key, now)

    def _allow_memory(self, key, now):
        with self._lock:
            if key not in self._fallback and len(self._fallback) >= 5000:
                expired = [
                    k
                    for k, hits in self._fallback.items()
                    if not hits or now - hits[-1] > self.window
                ]
                for old_key in expired:
                    del self._fallback[old_key]
                if len(self._fallback) >= 5000:
                    return False
            hits = self._fallback.setdefault(key, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
