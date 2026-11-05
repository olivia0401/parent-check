from types import SimpleNamespace

import pytest

import app as app_module
import ratelimit
from ratelimit import RateLimiter, RateLimitUnavailable


class RedisClient:
    def __init__(self):
        self.failing = False
        self.calls = []

    def ping(self):
        if self.failing:
            raise ConnectionError
        return True

    def register_script(self, _script):
        def script(**kwargs):
            if self.failing:
                raise ConnectionError
            self.calls.append(kwargs)
            return 1

        return script


def test_transient_failure_recovers_and_requests_have_unique_members(monkeypatch):
    client = RedisClient()
    monkeypatch.setattr(
        ratelimit, "redis", SimpleNamespace(Redis=SimpleNamespace(from_url=lambda *a, **kw: client))
    )
    limiter = RateLimiter(30, 60, redis_url="redis://test", fail_closed=True, retry_interval=0)
    assert limiter.allow("ip")
    client.failing = True
    with pytest.raises(RateLimitUnavailable):
        limiter.allow("ip")
    client.failing = False
    assert limiter.allow("ip") and limiter.backend == "redis"
    assert client.calls[0]["args"][3] != client.calls[1]["args"][3]


def test_production_rejects_costly_requests_when_shared_limiter_is_offline(monkeypatch):
    limiter = RateLimiter(30, 60, fail_closed=True)
    monkeypatch.setattr(limiter, "_connect", lambda: None)
    monkeypatch.setattr(app_module, "_limiter", limiter)
    monkeypatch.setattr(
        app_module, "_analyze_json", lambda *a: pytest.fail("Reached paid processing")
    )
    response = app_module.app.test_client().post("/api/check", json={"content": "hello"})
    assert response.status_code == 503
    assert response.get_json() == {"error": "rate_limiter_unavailable"}


def test_memory_capacity_cannot_reset_other_users_limits():
    limiter = RateLimiter(1, 60, fail_closed=False)
    for index in range(5000):
        assert limiter._allow_memory(str(index), 100)
    assert not limiter._allow_memory("new", 100)
    assert not limiter._allow_memory("0", 100)
    assert limiter._allow_memory("new", 161)
