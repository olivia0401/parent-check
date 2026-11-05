"""Run through stdin in the CI web container; never calls an LLM provider."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

assert os.geteuid() == 10001
mounted = Path("/run/secrets")
assert {p.name for p in mounted.iterdir()} == {"database_url", "secret_key", "gemini_api_key"}
assert len((mounted / "secret_key").read_text()) >= 32
assert not (mounted / "gemini_api_key").read_text()
assert os.environ["APP_ENV"] == "production"
assert os.environ.get("AWS_ACCESS_KEY_ID") is None

base = "http://127.0.0.1:8000"
for attempt in range(30):
    try:
        with urllib.request.urlopen(base + "/about", timeout=5) as response:
            assert response.status == 200
        break
    except (urllib.error.URLError, ConnectionError):
        if attempt == 29:
            raise
        time.sleep(1)

request = urllib.request.Request(
    base + "/api/check",
    data=json.dumps({"content": "hello"}).encode(),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    body = json.load(response)
    assert body["used_ai"] is False

try:
    urllib.request.urlopen(base + "/history/1", timeout=5)
    raise AssertionError("Private history was accessible")
except urllib.error.HTTPError as response:
    assert response.code == 404

print("Container security smoke checks passed.")
