"""No real Docker/AWS mutations: validate sequencing, readiness failure and rollback."""

import subprocess
import sys

import pytest

from ops import deploy as deployment
from ops.export_secrets import secret_files, write_snapshot

DOCUMENT = {"SECRET_KEY": "s" * 48, "POSTGRES_PASSWORD": "p" * 48, "GEMINI_API_KEY": ""}


def test_denied_secret_cannot_stop_or_touch_docker(tmp_path, monkeypatch):
    def denied(*args):
        raise PermissionError("PRIVATE_AWS_ERROR")

    monkeypatch.setattr(deployment, "fetch_document", denied)
    with pytest.raises(PermissionError):
        deployment.deploy(
            tmp_path,
            tmp_path / "secrets",
            "arn",
            "region",
            runner=lambda *a, **kw: pytest.fail("Docker called before secret validation"),
        )


def test_systemd_restart_has_no_stop_hook():
    from pathlib import Path

    unit = (Path(__file__).resolve().parents[1] / "ops/parent-check.service.example").read_text()
    assert not any(line.startswith("ExecStop=") for line in unit.splitlines())
    assert "-m ops.deploy" in unit


@pytest.mark.skipif(sys.platform != "linux", reason="Host filesystem semantics require Linux")
@pytest.mark.parametrize("fail", [False, True])
def test_ready_switch_or_rollback_preserves_previous_release(tmp_path, monkeypatch, fail):
    directory, state = tmp_path / "secrets", tmp_path / "state"
    write_snapshot(secret_files(DOCUMENT), directory)
    previous = (directory / "current").resolve()
    state.mkdir(mode=0o700)
    (state / "image").write_text("sha256:old")
    changed = {**DOCUMENT, "SECRET_KEY": "n" * 48}
    monkeypatch.setattr(deployment, "fetch_document", lambda *args: changed)
    switches = []

    def runner(command, *, env, **kwargs):
        if command[1] == "ps":
            return "container"
        if command[1] == "inspect":
            return "sha256:old"
        if command[1] == "image":
            return "sha256:new"
        if "up" in command:
            switches.append(env["WEB_IMAGE"])
            assert "--wait" in command and "--no-build" in command
            assert "PRIVATE" not in " ".join(command)
            if fail and env["WEB_IMAGE"] == "sha256:new":
                raise subprocess.CalledProcessError(1, command, stderr="PRIVATE_DOCKER_ERROR")
        return ""

    if fail:
        with pytest.raises(deployment.DeploymentError, match="previous image") as error:
            deployment.deploy(
                tmp_path,
                directory,
                "arn",
                "region",
                build=True,
                runner=runner,
                state_directory=state,
            )
        assert "PRIVATE_DOCKER_ERROR" not in str(error.value)
        assert switches == ["sha256:new", "sha256:old"]
        assert (directory / "current").resolve() == previous
        assert (state / "image").read_text() == "sha256:old"
    else:
        deployment.deploy(
            tmp_path, directory, "arn", "region", build=True, runner=runner, state_directory=state
        )
        assert switches == ["sha256:new"]
        assert (directory / "current" / "secret_key").read_text() == "n" * 48
        assert (state / "image").read_text() == "sha256:new"
        assert (previous / "secret_key").read_text() == "s" * 48


@pytest.mark.skipif(sys.platform != "linux", reason="Host filesystem semantics require Linux")
def test_reboot_uses_the_persisted_image_not_the_initial_tag(tmp_path, monkeypatch):
    state = tmp_path / "persistent"
    state.mkdir(mode=0o700)
    (state / "image").write_text("sha256:last-successful")
    monkeypatch.setattr(deployment, "fetch_document", lambda *a: DOCUMENT)
    inspected = []

    def runner(command, **kwargs):
        if command[1] == "ps":
            return ""
        if command[1] == "image":
            inspected.append(command[-1])
            return command[-1]
        return ""

    deployment.deploy(
        tmp_path, tmp_path / "fresh-run-dir", "arn", "region", runner=runner, state_directory=state
    )
    assert inspected == ["sha256:last-successful"]


@pytest.mark.skipif(sys.platform != "linux", reason="Host filesystem semantics require Linux")
def test_failed_build_leaves_running_release_and_secret_snapshot_untouched(tmp_path, monkeypatch):
    directory, state = tmp_path / "secrets", tmp_path / "state"
    write_snapshot(secret_files(DOCUMENT), directory)
    before = (directory / "current").resolve()
    state.mkdir(mode=0o700)
    (state / "image").write_text("sha256:old")
    monkeypatch.setattr(deployment, "fetch_document", lambda *args: DOCUMENT)

    def runner(command, **kwargs):
        assert "compose" not in command
        if command[1] == "ps":
            return "container"
        if command[1] == "inspect":
            return "sha256:old"
        if command[1] == "build":
            raise subprocess.CalledProcessError(1, command)
        return ""

    with pytest.raises(subprocess.CalledProcessError):
        deployment.deploy(
            tmp_path, directory, "arn", "region", build=True, runner=runner, state_directory=state
        )
    assert (directory / "current").resolve() == before
