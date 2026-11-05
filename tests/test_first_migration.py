"""Exercise password/Compose transitions, including partially applied failures."""

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops import first_migration as migration

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux host migration semantics")

OLD_PASSWORD = "old-db-pass"
DOCUMENT = {"SECRET_KEY": "s" * 48, "POSTGRES_PASSWORD": "n" * 64,
            "GEMINI_API_KEY": "synthetic-provider-key"}


class Denied(Exception):
    response = {"Error": {"Code": "AccessDeniedException"}}


class Secrets:
    def __init__(self, writable=False):
        self.writable = writable

    def get_secret_value(self, **kwargs):
        return {"VersionId": "a" * 32, "SecretString": json.dumps(DOCUMENT)}

    def put_secret_value(self, **kwargs):
        assert kwargs["ClientRequestToken"] == "a" * 32
        assert kwargs["SecretString"] == json.dumps(DOCUMENT)
        if not self.writable:
            raise Denied


class DockerModel:
    def __init__(self, root, old_root, backup, state, failure):
        self.root, self.old_root, self.backup, self.state = root, old_root, backup, state
        self.failure = failure
        self.password = OLD_PASSWORD
        self.up_calls = []
        self.sql_calls = []
        self.verifiers = {}
        self.commands = []
        self.active_new = False
        self.rows = []
        envs = {
            "web": {"SECRET_KEY": DOCUMENT["SECRET_KEY"], "GEMINI_API_KEY": DOCUMENT["GEMINI_API_KEY"],
                    "DATABASE_URL": "postgresql+psycopg2://parentcheck:" + OLD_PASSWORD + "@db:5432/parentcheck"},
            "db": {"POSTGRES_USER": "parentcheck", "POSTGRES_DB": "parentcheck",
                   "POSTGRES_PASSWORD": OLD_PASSWORD},
            "redis": {}, "caddy": {"SITE_ADDRESS": "example.invalid"},
        }
        mounts = {
            "db": [("pgdata", "/var/lib/postgresql/data")],
            "caddy": [("caddy_data", "/data"), ("caddy_config", "/config")],
        }
        for service in ("web", "db", "redis", "caddy"):
            self.rows.append({
                "Name": "/parent-check-" + service + "-1", "Image": "sha256:old-" + service,
                "Config": {"Env": [key + "=" + value for key, value in envs[service].items()],
                           "Labels": {"com.docker.compose.project": "parent-check",
                                      "com.docker.compose.project.config_files": str(old_root / "docker-compose.prod.yml")
                                      + ",/tmp/parent-check-existing-db-override.json"}},
                "Mounts": [{"Type": "volume", "Name": "parent-check_" + name, "Destination": target}
                           for name, target in mounts.get(service, [])],
            })
        self.before = copy.deepcopy(self.rows)

    def run(self, command, **kwargs):
        self.commands.append(command)
        # Passwords only travel through stdin or the Secrets API, never argv.
        assert OLD_PASSWORD not in " ".join(command)
        assert DOCUMENT["POSTGRES_PASSWORD"] not in " ".join(command)
        if command[1] == "inspect":
            value = json.dumps(self.rows)
        elif command[1:3] == ["image", "inspect"]:
            value = "sha256:candidate"
        elif command[1] == "compose":
            if "--format" in command:
                volumes = {key: {"name": "parent-check_" + key}
                           for key in ("pgdata", "caddy_data", "caddy_config")}
                if self.failure == "volume":
                    volumes["pgdata"]["name"] = "wrong-empty-volume"
                value = json.dumps({"volumes": volumes})
            elif "up" in command:
                self.up_calls.append(command)
                assert "down" not in command and "--no-build" in command
                if command[-2:] != ["db", "redis"]:
                    recovery_path = command[command.index("up") - 1]
                    recovery = json.loads(Path(recovery_path).read_text())
                    for row, service in zip(self.rows, ("web", "db", "redis", "caddy")):
                        captured = recovery["services"][service]
                        row["Image"] = captured["image"]
                        row["Config"]["Env"] = [key + "=" + value for key, value in captured["environment"].items()]
                    self.active_new = False
                value = ""
            else:
                value = ""
        elif "pg_dump" in command:
            if self.failure == "backup":
                raise subprocess.CalledProcessError(1, command)
            kwargs["stdout"].write(b"synthetic custom dump")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        elif "pg_restore" in command:
            assert kwargs["stdin"].read() == b"synthetic custom dump"
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        elif "psql" in command:
            assert OLD_PASSWORD not in kwargs["input"]
            assert DOCUMENT["POSTGRES_PASSWORD"] not in kwargs["input"]
            verifier = kwargs["input"].split("WITH PASSWORD '", 1)[1][:-3]
            self.password = self.verifiers[verifier]
            self.sql_calls.append(self.password)
            if self.failure == "alter" and self.password == DOCUMENT["POSTGRES_PASSWORD"]:
                return SimpleNamespace(returncode=1, stdout="", stderr="PRIVATE " + self.password)
            value = ""
        elif "python" in command:
            code = command[-1]
            if "encrypt_password" in code:
                passwords = json.loads(kwargs["input"])
                encrypted = ["SCRAM-SHA-256$" + hashlib.sha256(value.encode()).hexdigest() for value in passwords]
                self.verifiers = dict(zip(encrypted, passwords))
                value = json.dumps(encrypted)
                return SimpleNamespace(returncode=0, stdout=value, stderr="")
            elif "psycopg2" in code:
                assert json.loads(kwargs["input"])["password"] == self.password
            elif "healthz" in code and self.failure == "health":
                return SimpleNamespace(returncode=1, stdout="", stderr="PRIVATE HEALTH ERROR")
            value = ""
        else:
            raise AssertionError(command)
        return SimpleNamespace(returncode=0, stdout=value, stderr="")

    def deploy(self, *args, **kwargs):
        assert self.password == DOCUMENT["POSTGRES_PASSWORD"]
        assert kwargs["initial_migration"] is True
        self.active_new = True
        self.rows[0]["Image"] = "sha256:candidate"
        self.rows[0]["Config"]["Env"] = ["SECRET_KEY_FILE=/run/secrets/secret_key"]
        if self.failure == "switch":
            raise RuntimeError("PRIVATE " + DOCUMENT["POSTGRES_PASSWORD"])
        self.state.mkdir(mode=0o700)
        (self.state / "image").write_text("sha256:candidate")


def setup(tmp_path, monkeypatch, failure=None):
    root, old_root, backup, state = [tmp_path / name for name in ("new", "old", "backup", "state")]
    for folder in (root, old_root, backup):
        folder.mkdir(mode=0o700)
    for name in ("database.dump", "source-config.tar.gz", "parent-check-existing-db-override.json"):
        (backup / name).write_text("fixture")
    (old_root / "docker-compose.prod.yml").write_text("fixture")
    docker = DockerModel(root, old_root, backup, state, failure)
    monkeypatch.setattr(migration.subprocess, "run", docker.run)
    monkeypatch.setattr(migration.time, "sleep", lambda *_: None)
    return docker, dict(root=root, old_root=old_root, backup=backup, arn="arn", region="eu-west-2",
                        client=Secrets(), deploy_action=docker.deploy, state_directory=state)


def test_success_keeps_data_and_certificates_and_changes_password(tmp_path, monkeypatch):
    docker, kwargs = setup(tmp_path, monkeypatch)
    migration.migrate(**kwargs)
    assert docker.password == DOCUMENT["POSTGRES_PASSWORD"]
    assert docker.active_new
    assert (docker.state / "image").read_text() == "sha256:candidate"
    assert [row["Mounts"] for row in docker.rows] == [row["Mounts"] for row in docker.before]
    assert not docker.up_calls  # Normal switch is delegated to the existing, tested deploy command.


@pytest.mark.parametrize("failure", ["alter", "switch", "health"])
def test_partial_failure_restores_password_image_environment_and_metadata(
    tmp_path, monkeypatch, failure, capsys
):
    docker, kwargs = setup(tmp_path, monkeypatch, failure)
    with pytest.raises(migration.MigrationError, match="restored"):
        migration.migrate(**kwargs)
    assert docker.password == OLD_PASSWORD
    assert not docker.active_new
    assert docker.rows == docker.before
    assert not (docker.state / "image").exists()
    assert bool(docker.up_calls) == (failure != "alter")
    visible = capsys.readouterr()
    assert DOCUMENT["POSTGRES_PASSWORD"] not in visible.out + visible.err
    assert "PRIVATE" not in visible.out + visible.err
    assert OLD_PASSWORD not in visible.out + visible.err
    for path in docker.backup.iterdir():
        if path.name.startswith(("migration-private-", "recovery-", "pre-cutover-")):
            assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize("failure", ["volume", "backup"])
def test_preflight_failure_never_rotates_password_or_replaces_containers(tmp_path, monkeypatch, failure):
    docker, kwargs = setup(tmp_path, monkeypatch, failure)
    with pytest.raises((migration.MigrationError, subprocess.CalledProcessError)):
        migration.migrate(**kwargs)
    assert docker.password == OLD_PASSWORD
    assert not docker.sql_calls and not docker.up_calls
    assert docker.rows == docker.before


def test_still_writable_role_cannot_start_migration(tmp_path, monkeypatch):
    docker, kwargs = setup(tmp_path, monkeypatch)
    kwargs["client"] = Secrets(writable=True)
    with pytest.raises(migration.MigrationError, match="temporary"):
        migration.migrate(**kwargs)
    assert not docker.sql_calls and not docker.up_calls
    assert docker.rows == docker.before
