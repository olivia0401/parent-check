"""Prepare secrets/image before replacing containers; restore a known previous release on failure."""

import argparse
import os
import subprocess
import sys
import uuid
from pathlib import Path

from ops.export_secrets import fetch_document, secret_files, write_snapshot


class DeploymentError(RuntimeError):
    pass


def _run(command, *, cwd, env, timeout=180):
    # Captured CLI/build errors may contain configuration. Never echo them.
    return subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=True, timeout=timeout
    ).stdout.strip()


def _restore_snapshot(directory, previous):
    link = directory / (".restore-" + uuid.uuid4().hex)
    link.symlink_to(previous.name, target_is_directory=True)
    os.replace(link, directory / "current")


def deploy(
    root,
    directory,
    secret_arn,
    region,
    *,
    db_user="parentcheck",
    db_name="parentcheck",
    project="parent-check",
    build=False,
    initial_migration=False,
    state_directory="/var/lib/parent-check",
    runner=_run,
):
    root, directory, state_directory = Path(root), Path(directory), Path(state_directory)
    # Nothing, including Docker, is changed if AWS access/validation fails.
    files = secret_files(fetch_document(secret_arn, region), db_user, db_name)
    state_directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_info = state_directory.lstat()
    if (
        state_directory.is_symlink()
        or state_info.st_uid != os.geteuid()
        or state_info.st_mode & 0o077
    ):
        raise DeploymentError(
            "Release metadata directory must be private and owned by the operator"
        )
    current = directory / "current"
    previous = current.resolve() if current.is_symlink() else None
    # Only non-secret image metadata survives a reboot. Secret snapshots stay volatile.
    release_file = state_directory / "image"
    if release_file.is_symlink():
        raise DeploymentError("Release metadata must be a regular file")
    has_baseline = previous is not None and release_file.exists()
    if previous and (previous / "postgres_password").read_text() != files["postgres_password"]:
        raise DeploymentError(
            "Coordinate DB password rotation separately; deployment did not change services"
        )
    environment = dict(os.environ, SECRETS_DIRECTORY=str(current))

    def run(command, **kwargs):
        return runner(command, cwd=root, env=environment, **kwargs)

    old_container = run(
        [
            "docker",
            "ps",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
            "--filter",
            "label=com.docker.compose.service=web",
        ]
    )
    old_image = (
        run(["docker", "inspect", "--format", "{{.Image}}", old_container])
        if old_container
        else None
    )
    if old_image and not has_baseline and not initial_migration:
        raise DeploymentError(
            "First migration requires the documented backup and --initial-migration"
        )
    image = release_file.read_text().strip() if release_file.exists() else "parent-check-web:local"
    if build:
        image = "parent-check-release:" + uuid.uuid4().hex
        run(["docker", "build", "-t", image, "."], timeout=900)
    # Pin the exact image so future boot/secret refresh does not pull a new tag.
    image = run(["docker", "image", "inspect", "--format", "{{.Id}}", image])
    if not image:
        raise DeploymentError("No built web image is available")
    temporary = state_directory / (".image-" + uuid.uuid4().hex)
    temporary.write_text(image, encoding="utf-8")
    write_snapshot(files, directory)
    compose = ["docker", "compose", "-p", project, "-f", "docker-compose.prod.yml"]
    up = ["up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "90"]
    environment["WEB_IMAGE"] = image
    try:
        run([*compose, "config", "--quiet"])
        run([*compose, *up])
        os.replace(temporary, release_file)
    except Exception:
        temporary.unlink(missing_ok=True)
        if has_baseline and old_image:
            _restore_snapshot(directory, previous)
            environment["WEB_IMAGE"] = old_image
            try:
                run([*compose, *up])
            except Exception:
                raise DeploymentError(
                    "Deployment and rollback failed; operator recovery required"
                ) from None
            raise DeploymentError(
                "Deployment failed; previous image and secret snapshot restored"
            ) from None
        raise DeploymentError(
            "Initial deployment failed; restore the documented migration backup"
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--directory", default="/run/parent-check")
    parser.add_argument("--state-directory", default="/var/lib/parent-check")
    parser.add_argument("--project", default="parent-check")
    parser.add_argument("--db-user", default="parentcheck")
    parser.add_argument("--db-name", default="parentcheck")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--initial-migration", action="store_true")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run as root on the Linux host")
    if not Path(args.directory).resolve().is_relative_to(Path("/run")):
        parser.error("Secret snapshots must stay under /run")
    if not Path(args.state_directory).resolve().is_relative_to(Path("/var/lib")):
        parser.error("Image metadata must stay under /var/lib")
    try:
        deploy(
            Path(__file__).resolve().parent.parent,
            args.directory,
            args.secret_arn,
            args.region,
            project=args.project,
            db_user=args.db_user,
            db_name=args.db_name,
            state_directory=args.state_directory,
            build=args.build,
            initial_migration=args.initial_migration,
        )
    except DeploymentError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f"Preparation failed ({type(exc).__name__}); no fallback credentials were used.",
            file=sys.stderr,
        )
        return 1
    print("Deployment healthy.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
