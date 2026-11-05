"""Coordinate an existing EC2 database password change with the first secret-mounted release.

Run as root through systemd-run. Backup files contain credentials and stay private.
This does not install the normal boot unit or delete any data volume.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import unquote, urlsplit


class MigrationError(RuntimeError):
    pass


def _client(region):
    import boto3
    from botocore.config import Config

    os.environ["AWS_EC2_METADATA_V1_DISABLED"] = "true"
    session = boto3.Session(region_name=region)
    credentials = session.get_credentials()
    if credentials is None or credentials.method != "iam-role":
        raise MigrationError("An EC2 instance role is required")
    return session.client("secretsmanager", config=Config(
        connect_timeout=3, read_timeout=5, retries={"max_attempts": 2},
    ))


def _environment(container):
    return dict(item.split("=", 1) for item in container["Config"]["Env"] if "=" in item)


def _volume(container, target):
    matches = [mount for mount in container["Mounts"] if mount["Destination"] == target]
    if len(matches) != 1 or matches[0]["Type"] != "volume":
        raise MigrationError("Expected an existing named data volume")
    return matches[0]["Name"]


def migrate(root, old_root, backup, arn, region, *, project="parent-check", client=None,
            deploy_action=None, state_directory="/var/lib/parent-check"):
    from ops.deploy import deploy
    from ops.export_secrets import secret_files

    root, old_root, backup = (Path(path).resolve() for path in (root, old_root, backup))
    if root == old_root or not re.fullmatch(r"[a-zA-Z0-9_-]+", project):
        raise MigrationError("Use a separate release checkout and the existing project name")
    info = backup.stat()
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise MigrationError("The existing backup directory must be private")
    if not (backup / "database.dump").is_file() or not (backup / "source-config.tar.gz").is_file():
        raise MigrationError("The documented database and configuration backups are required")
    release_file = Path(state_directory) / "image"
    if release_file.exists() or release_file.is_symlink():
        raise MigrationError("A migrated release already exists; use ops.deploy for updates")
    os.umask(0o077)
    log = backup / ("migration-private-" + uuid.uuid4().hex + ".log")

    def run(command, *, cwd=root, env=None, timeout=180, input=None, **kwargs):
        try:
            result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                                    input=input, capture_output=True, text=True, **kwargs)
        except subprocess.TimeoutExpired:
            raise MigrationError("A migration command timed out") from None
        if result.returncode:
            with log.open("a", encoding="utf-8") as output:
                output.write((result.stdout or "") + (result.stderr or ""))
            raise MigrationError("A migration command failed; private diagnostics saved")
        return result.stdout.strip()

    def inspect(names):
        return json.loads(run(["docker", "inspect", *names]))

    names = [f"{project}-{service}-1" for service in ("web", "db", "redis", "caddy")]
    rows = inspect(names)
    web, db, redis, caddy = rows
    if any(row["Config"]["Labels"].get("com.docker.compose.project") != project for row in rows):
        raise MigrationError("Container project does not match")
    web_env, db_env = _environment(web), _environment(db)
    old_password = db_env.get("POSTGRES_PASSWORD", "")
    url = urlsplit(web_env.get("DATABASE_URL", ""))
    if (not old_password or unquote(url.password or "") != old_password
            or url.hostname != "db" or unquote(url.username or "") != "parentcheck"
            or url.path != "/parentcheck" or db_env.get("POSTGRES_USER") != "parentcheck"
            or db_env.get("POSTGRES_DB") != "parentcheck"):
        raise MigrationError("This migration requires the verified parentcheck database configuration")

    client = client or _client(region)
    response = client.get_secret_value(SecretId=arn, VersionStage="AWSCURRENT")
    document = json.loads(response["SecretString"])
    secret_files(document)
    if (document["SECRET_KEY"] != web_env.get("SECRET_KEY")
            or document["GEMINI_API_KEY"] != web_env.get("GEMINI_API_KEY", "")
            or document["POSTGRES_PASSWORD"] == old_password):
        raise MigrationError("Staged credentials do not match the intended first migration")
    # Reuse the exact version and bytes: this is a no-op even if write access remains.
    # Require effective denial before the first database mutation.
    try:
        client.put_secret_value(SecretId=arn, ClientRequestToken=response["VersionId"],
                                SecretString=response["SecretString"])
    except Exception as error:
        if getattr(error, "response", {}).get("Error", {}).get("Code") not in {
            "AccessDeniedException", "AccessDenied"
        }:
            raise MigrationError("Could not verify removal of temporary write access") from None
    else:
        raise MigrationError("Remove parent-check-secret-migration-temporary, then retry")

    compose = ["docker", "compose", "-p", project, "-f", "docker-compose.prod.yml"]
    model = json.loads(run([*compose, "config", "--format", "json"]))
    volumes = {
        "pgdata": _volume(db, "/var/lib/postgresql/data"),
        "caddy_data": _volume(caddy, "/data"),
        "caddy_config": _volume(caddy, "/config"),
    }
    if any(model["volumes"][key]["name"] != name for key, name in volumes.items()):
        raise MigrationError("New configuration would change a data or certificate volume")
    candidate = run(["docker", "image", "inspect", "--format", "{{.Id}}", "parent-check-web:local"])
    if not candidate.startswith("sha256:"):
        raise MigrationError("A built candidate image is required")

    # Recreate the original web stack with captured environments/images, rather
    # than combining the different config-file labels reported by compose ls.
    recovery = {"services": {}, "volumes": {
        key: {"external": True, "name": name} for key, name in volumes.items()
    }}
    for service, row in zip(("web", "db", "redis", "caddy"), rows):
        recovery["services"][service] = {"image": row["Image"], "environment": _environment(row)}
    recovery_path = backup / ("recovery-" + uuid.uuid4().hex + ".json")
    recovery_path.write_text(json.dumps(recovery), encoding="utf-8")
    original_files = web["Config"]["Labels"]["com.docker.compose.project.config_files"].split(",")
    old_compose = ["docker", "compose", "-p", project, "--project-directory", str(old_root)]
    for name in original_files:
        path = Path(name)
        if path.name == "parent-check-existing-db-override.json":
            path = backup / path.name
        elif not path.resolve().is_relative_to(old_root):
            raise MigrationError("Original Compose file is outside the backed-up checkout")
        if not path.is_file():
            raise MigrationError("An original Compose file required for recovery is missing")
        old_compose.extend(["-f", str(path)])
    old_compose.extend(["-f", str(recovery_path)])
    run([*old_compose, "config", "--quiet"], cwd=old_root)

    def auth(password):
        code = ("import json,sys,psycopg2; p=json.load(sys.stdin); "
                "c=psycopg2.connect(**p,connect_timeout=5); "
                "q=c.cursor(); q.execute('SELECT 1'); assert q.fetchone()==(1,); c.close()")
        run(["docker", "exec", "-i", names[0], "python", "-c", code], timeout=20,
            input=json.dumps({"host": "db", "user": "parentcheck", "dbname": "parentcheck",
                              "password": password}))

    def alter(password):
        # libpq prepares salted SCRAM verifiers before any mutation. The real
        # password is never included in SQL, even if statement logging is on.
        sql = "ALTER ROLE parentcheck WITH PASSWORD '" + verifiers[password] + "';\n"
        run(["docker", "exec", "-i", names[1], "psql", "-U", "parentcheck", "-d", "parentcheck",
             "-X", "-v", "ON_ERROR_STOP=1", "-q"], input=sql, timeout=30)

    def http_ready(path):
        code = ("import urllib.request; "
                f"r=urllib.request.urlopen('http://127.0.0.1:8000/{path}',timeout=3); "
                "assert r.status==200")
        for attempt in range(20):
            try:
                run(["docker", "exec", names[0], "python", "-c", code], timeout=8)
                return
            except MigrationError:
                if attempt == 19:
                    raise
                time.sleep(1)

    auth(old_password)
    encryption_code = (
        "import json,sys,psycopg2; from psycopg2.extensions import encrypt_password; "
        "p=json.load(sys.stdin); c=psycopg2.connect(host='db',user='parentcheck',"
        "dbname='parentcheck',password=p[0],connect_timeout=5); "
        "v=[encrypt_password(value,'parentcheck',c,algorithm='scram-sha-256') for value in p]; "
        "c.close(); print(json.dumps(v))"
    )
    encrypted = json.loads(run(
        ["docker", "exec", "-i", names[0], "python", "-c", encryption_code], timeout=20,
        input=json.dumps([old_password, document["POSTGRES_PASSWORD"]]),
    ))
    if (len(encrypted) != 2 or any(
        not isinstance(value, str) or not value.startswith("SCRAM-SHA-256$")
        or not re.fullmatch(r"[a-zA-Z0-9+/$:=.-]+", value) for value in encrypted
    )):
        raise MigrationError("Could not prepare client-side SCRAM password verifiers")
    verifiers = dict(zip((old_password, document["POSTGRES_PASSWORD"]), encrypted))
    fresh = backup / ("pre-cutover-" + uuid.uuid4().hex + ".dump")
    with fresh.open("xb") as output:
        subprocess.run(["docker", "exec", names[1], "pg_dump", "-U", "parentcheck", "-d",
                        "parentcheck", "-Fc"], stdout=output, stderr=subprocess.PIPE,
                       check=True, timeout=90)
    if not fresh.stat().st_size:
        raise MigrationError("Fresh database backup is empty")
    with fresh.open("rb") as source:
        subprocess.run(["docker", "exec", "-i", names[1], "pg_restore", "--list"],
                       stdin=source, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       check=True, timeout=30)
    print("Preflight PASS: permissions, credential match, volumes, recovery config and fresh backup.", flush=True)
    switching = False
    try:
        print("Changing database password and checking authentication...", flush=True)
        alter(document["POSTGRES_PASSWORD"])
        auth(document["POSTGRES_PASSWORD"])
        if run(["docker", "image", "inspect", "--format", "{{.Id}}", "parent-check-web:local"]) != candidate:
            raise MigrationError("Candidate image changed during preparation")
        switching = True
        (deploy_action or deploy)(root, "/run/parent-check", arn, region, project=project,
                                  initial_migration=True, runner=run,
                                  state_directory=state_directory)
        auth(document["POSTGRES_PASSWORD"])
        http_ready("healthz")
    except Exception as error:
        print(f"Switch failed ({type(error).__name__}); restoring the previous release...", flush=True)
        try:
            up = ["up", "-d", "--no-build", "--force-recreate", "--wait", "--wait-timeout", "90"]
            if switching:
                run([*old_compose, *up, "db", "redis"], cwd=old_root)
            alter(old_password)
            if switching:
                run([*old_compose, *up], cwd=old_root)
            auth(old_password)
            http_ready("about")
            release_file.unlink(missing_ok=True)
        except Exception as recovery_error:
            raise MigrationError(
                "RECOVERY REQUIRED: automatic restoration failed ("
                + type(recovery_error).__name__ + "); keep the SSM session open"
            ) from None
        raise MigrationError("Previous database password and web release restored; staged secret retained") from None
    print("FIRST MIGRATION HEALTHY: database authentication and /healthz passed.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--old-root", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--project", default="parent-check")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run as root on the Linux EC2 host")
    sys.path.insert(0, str(Path(args.root).resolve()))

    def interrupted(signum, frame):
        raise MigrationError("Migration interrupted")

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        migrate(args.root, args.old_root, args.backup_dir, args.secret_arn, args.region,
                project=args.project)
    except Exception as error:
        message = str(error) if isinstance(error, MigrationError) else type(error).__name__
        print("Migration stopped: " + message, file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
