"""Security boundaries: startup secrets, invalid requests and record ownership."""

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from sqlalchemy.engine import make_url

import app as app_module
import observability
import repo
from ops import export_secrets
from ratelimit import RateLimiter
from runtime_secrets import SECRET_NAMES, load_secret_files, validate_session_key

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_module, "_limiter", RateLimiter(1000, 60))
    monkeypatch.setattr(app_module, "_llm", None)
    return app_module.app.test_client()


def test_mounted_secrets_load_before_database_initialization(tmp_path):
    key = tmp_path / "key"
    url = tmp_path / "database"
    key.write_text("s" * 48, encoding="utf-8")
    url.write_text("sqlite:///:memory:", encoding="utf-8")
    excluded = {*SECRET_NAMES, *(f"{name}_FILE" for name in SECRET_NAMES), "APP_ENV", "RENDER"}
    env = {name: value for name, value in os.environ.items() if name not in excluded}
    env.update({"APP_ENV": "production", "SECRET_KEY_FILE": str(key),
                "DATABASE_URL_FILE": str(url), "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.run(
        [sys.executable, "-c", "import app; import db; assert db.DATABASE_URL == 'sqlite:///:memory:'"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert key.read_text() not in proc.stdout + proc.stderr


def test_file_failure_has_no_fallback_and_no_value_disclosure(tmp_path):
    env = {"SECRET_KEY_FILE": str(tmp_path / "missing")}
    with pytest.raises(RuntimeError, match="Cannot load SECRET_KEY_FILE"):
        load_secret_files(env)
    assert "SECRET_KEY" not in env
    value = "sensitive-marker"
    with pytest.raises(RuntimeError) as error:
        load_secret_files({"SECRET_KEY": value, **env})
    assert value not in str(error.value)


def test_secret_loader_publishes_no_partial_config(tmp_path):
    key = tmp_path / "key"
    key.write_text("s" * 48)
    env = {"SECRET_KEY_FILE": str(key), "DATABASE_URL_FILE": str(tmp_path / "missing")}
    with pytest.raises(RuntimeError):
        load_secret_files(env)
    assert "SECRET_KEY" not in env


@pytest.mark.parametrize("value", [None, "short", "change-me" * 8,
                                       "dev-only-key-not-for-production"])
def test_production_rejects_known_weak_session_keys(value):
    with pytest.raises(RuntimeError):
        validate_session_key(value)


def test_export_encodes_password_and_keeps_it_out_of_errors():
    password = "p@ss:/?#%" * 5
    files = export_secrets.secret_files({
        "SECRET_KEY": "s" * 48, "POSTGRES_PASSWORD": password, "GEMINI_API_KEY": "",
    })
    assert files["postgres_password"] == password
    assert make_url(files["database_url"]).password == password
    assert files["gemini_api_key"] == ""
    with pytest.raises(ValueError) as error:
        export_secrets.secret_files({"POSTGRES_PASSWORD": password})
    assert password not in str(error.value)


@pytest.mark.parametrize("method", ["env", "shared-credentials-file", "assume-role"])
def test_exporter_refuses_non_instance_credentials(monkeypatch, method):
    # The SDK is installed only on the host; deterministic tests supply a fake.
    session = SimpleNamespace(get_credentials=lambda: SimpleNamespace(method=method))
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=lambda **kw: session))
    monkeypatch.setitem(sys.modules, "botocore.config", SimpleNamespace(Config=lambda **kw: kw))
    with pytest.raises(RuntimeError, match="instance role"):
        export_secrets.fetch_document("secret-arn", "eu-west-2")


def test_exporter_reads_only_current_version_of_requested_secret(monkeypatch):
    calls = []
    document = {"SECRET_KEY": "s" * 48, "POSTGRES_PASSWORD": "p" * 48, "GEMINI_API_KEY": ""}

    def get_secret_value(**kwargs):
        calls.append(kwargs)
        return {"SecretString": json.dumps(document)}

    session = SimpleNamespace(
        get_credentials=lambda: SimpleNamespace(method="iam-role"),
        client=lambda *a, **kw: SimpleNamespace(get_secret_value=get_secret_value),
    )
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=lambda **kw: session))
    monkeypatch.setitem(sys.modules, "botocore.config", SimpleNamespace(Config=lambda **kw: kw))
    assert export_secrets.fetch_document("secret-arn", "eu-west-2") == document
    assert calls == [{"SecretId": "secret-arn", "VersionStage": "AWSCURRENT"}]


@pytest.mark.skipif(sys.platform != "linux", reason="EC2 host permissions require Linux")
def test_snapshot_rotation_is_atomic_and_readable_by_container_uid(tmp_path):
    private = tmp_path / "private"
    export_secrets.write_snapshot({"secret_key": "old"}, private)
    old_file = (private / "current" / "secret_key").resolve()
    assert private.stat().st_mode & 0o777 == 0o700
    assert old_file.stat().st_mode & 0o777 == 0o444
    export_secrets.write_snapshot({"secret_key": "new"}, private)
    assert old_file.read_text() == "old"
    assert (private / "current" / "secret_key").read_text() == "new"
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(RuntimeError, match="private"):
        export_secrets.write_snapshot({"secret_key": "x"}, public)


@pytest.mark.parametrize("payload", [[], [1], None, "text", 42, False])
def test_json_must_be_an_object(client, payload):
    response = client.post("/api/check", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_json_object"


@pytest.mark.parametrize("field,value", [("content", ["text"]), ("content", 42),
                                         ("source", {}), ("lang", ["en"]), ("lang", None)])
def test_api_rejects_wrong_field_types_before_ai(client, field, value, monkeypatch):
    def unexpected(*a, **kw):
        pytest.fail("Invalid input reached analysis")

    monkeypatch.setattr(app_module, "_analyze_json", unexpected)
    response = client.post("/api/check", json={"content": "hello", field: value})
    assert response.status_code == 400


def test_invalid_envelopes_rejected_before_database(client, monkeypatch):
    def unexpected():
        pytest.fail("Invalid request reached database")

    monkeypatch.setattr(app_module, "_db_ready", False)
    monkeypatch.setattr(app_module.db, "init_db", unexpected)
    assert client.post("/api/check", data="text").status_code == 415
    assert client.post("/api/policy-check", data="{", content_type="application/json").status_code == 400
    response = client.post("/api/check", json={"content": "x" * (64 * 1024)})
    assert response.status_code == 413
    assert response.get_json()["error"] == "payload_too_large"


def test_oversize_multipart_and_text_are_rejected(client):
    response = client.post("/api/check-image", data={
        "image": (io.BytesIO(b"x" * (app_module.app.config["MAX_CONTENT_LENGTH"] + 1)), "x.png"),
    })
    assert response.status_code == 413
    assert client.post("/api/check", json={"content": "x" * 5001}).status_code == 400


def test_cross_browser_feedback_and_deletion_cannot_change_owner_data(client):
    client.get("/history")
    with client.session_transaction() as state:
        owner = state["uid"]
    check_id = repo.create_check("other", "danger", "scam", [], owner)
    other = app_module.app.test_client()
    with other.session_transaction() as state:
        state["csrf"] = "outsider-csrf"
    assert other.get(f"/history/{check_id}").status_code == 404
    assert other.get("/history/99999999").status_code == 404
    assert other.post(f"/feedback/{check_id}", data={
        "helpful": "yes", "csrf_token": "outsider-csrf",
    }).status_code == 404
    assert repo.get_check(check_id, owner).helpful is None
    assert other.post("/history/clear", data={"csrf_token": "outsider-csrf"}).status_code == 302
    assert repo.get_check(check_id, owner) is not None


def test_api_rate_limit_uses_json_and_retry_after(client, monkeypatch):
    monkeypatch.setattr(app_module, "_limiter", RateLimiter(1, 60))
    assert client.post("/api/check", json={"content": "hello"}).status_code == 200
    response = client.post("/api/check", json={"content": "hello"})
    assert response.status_code == 429
    assert response.get_json() == {"error": "rate_limited"}
    assert int(response.headers["Retry-After"]) > 0


def test_database_failure_does_not_disclose_credentials(client, monkeypatch, caplog):
    marker = "private-db-password-marker"

    def fail():
        raise RuntimeError(marker)

    monkeypatch.setattr(app_module, "_db_ready", False)
    monkeypatch.setattr(app_module.db, "init_db", fail)
    response = client.post("/api/check", json={"content": "hello"})
    assert response.status_code == 503
    assert marker not in response.get_data(as_text=True) + caplog.text


def test_sensitive_responses_are_not_cached(client):
    response = client.post("/api/check", json={"content": "hello"})
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_log_formatter_redacts_keys_and_database_password(monkeypatch):
    marker = "sensitive-log-marker"
    password = "database-password-marker"
    monkeypatch.setenv("GEMINI_API_KEY", marker)
    monkeypatch.setenv("DATABASE_URL", f"postgresql://user:{password}@db/app")
    record = logging.LogRecord("test", logging.ERROR, "", 0, "%s %s", (marker, password), None)
    output = observability._JsonFormatter().format(record)
    assert marker not in output and password not in output
    assert "[REDACTED]" in output


def test_api_response_does_not_expose_credentials(client, monkeypatch):
    marker = "sensitive-api-response-marker"
    monkeypatch.setenv("GEMINI_API_KEY", marker)
    response = client.post("/api/check", json={"content": "hello"})
    assert response.status_code == 200
    assert marker not in response.get_data(as_text=True)


def test_compose_limits_secret_and_network_access():
    stack = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
    services = stack["services"]
    assert {name for name, service in services.items() if "ports" in service} == {"caddy"}
    assert stack["networks"]["data"]["internal"] is True
    assert services["db"]["networks"] == services["redis"]["networks"] == ["data"]
    assert services["caddy"]["networks"] == ["edge"]
    assert set(services["db"]["secrets"]) == {"postgres_password"}
    assert set(services["web"]["secrets"]) == {"database_url", "secret_key", "gemini_api_key"}
    assert "secrets" not in services["caddy"] and "secrets" not in services["redis"]
    assert services["web"]["environment"]["APP_ENV"] == "production"
    assert services["web"]["read_only"] is True
    policy = json.loads((ROOT / "ops/ec2-secret-policy.example.json").read_text())
    assert policy["Statement"][0]["Action"] == "secretsmanager:GetSecretValue"
    assert "*" not in policy["Statement"][0]["Resource"]
