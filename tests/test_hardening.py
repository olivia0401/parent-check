"""Regression tests for deployment hardening and agent-tool edge cases."""

import os
import subprocess
import sys
import time
from pathlib import Path

import app as app_module
from ai import tools
from ratelimit import RateLimiter

REPO_ROOT = Path(__file__).resolve().parent.parent


# --- production config ------------------------------------------------------

def _import_app(extra_env):
    env = {k: v for k, v in os.environ.items()
           if k not in ("SECRET_KEY", "APP_ENV", "RENDER", "GEMINI_API_KEY")}
    env.update({"DATABASE_URL": "sqlite:///:memory:", "PYTHONDONTWRITEBYTECODE": "1"})
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", "import app"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
    )


def test_production_refuses_to_start_without_secret_key():
    proc = _import_app({"APP_ENV": "production"})
    assert proc.returncode != 0
    assert "SECRET_KEY must be set" in proc.stderr


def test_production_with_secret_key_starts():
    proc = _import_app({"APP_ENV": "production", "SECRET_KEY": "x" * 32})
    assert proc.returncode == 0, proc.stderr


def test_is_production_reads_app_env(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert app_module.is_production()
    monkeypatch.setenv("APP_ENV", "development")
    assert not app_module.is_production()


# --- rate limit can't be dodged with a forged X-Forwarded-For ---------------

def test_forged_forwarded_for_does_not_bypass_rate_limit(monkeypatch):
    monkeypatch.setattr(app_module, "_limiter", RateLimiter(2, 60))
    client = app_module.app.test_client()
    codes = []
    for i in range(4):
        # The client forges the first hop; the trusted proxy appends the real IP.
        r = client.post("/check", data={"content": "x"},
                        headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"})
        codes.append(r.status_code)
    assert codes[-1] == 429


# --- tools ----------------------------------------------------------------

def test_short_helplines_are_detected():
    out = tools.execute_check_phone("Call 159 or 999 now", "en")
    types = {n["number"]: n["type"] for n in out["numbers"]}
    assert types == {"159": "UK official helpline", "999": "UK official helpline"}
    out = tools.execute_check_phone("请拨打96110", "zh")
    assert out["numbers"][0]["number"] == "96110"


class _SlowRag:
    def retrieve_similar(self, text, n=3, category=None):
        time.sleep(2)
        return []


def test_run_tools_parallel_enforces_deadline(monkeypatch):
    monkeypatch.setattr(tools, "TOOL_TIMEOUT_S", 0.2)
    calls = [
        {"name": "query_knowledge_base", "args": {"text": "hi"}},
        {"name": "check_phone_numbers", "args": {"text": "call 07700 900123"}},
    ]
    t0 = time.monotonic()
    results = tools.run_tools_parallel(calls, _SlowRag(), "en", "hi")
    assert time.monotonic() - t0 < 1.5
    by_name = {r["name"]: r["response"] for r in results}
    assert by_name["query_knowledge_base"] == {"error": "timeout"}
    assert by_name["check_phone_numbers"]["found"] is True


# --- startup order: seed the knowledge base only after the schema exists ----

def test_knowledge_base_seeded_after_schema_init(monkeypatch):
    import threading

    order = []
    seeded = threading.Event()
    monkeypatch.setattr(app_module, "_db_ready", False)
    monkeypatch.setattr(app_module.db, "init_db", lambda: order.append("init_db"))

    def fake_seed():
        order.append("seed")
        seeded.set()

    monkeypatch.setattr(app_module, "_seed_knowledge_bases", fake_seed)
    app_module.app.test_client().get("/about")
    assert seeded.wait(5)
    assert order == ["init_db", "seed"]
