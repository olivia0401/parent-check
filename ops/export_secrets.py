"""Fetch one EC2 secret through its instance role into private /run files.

Run as root on Linux. No values are printed, written to the repo or passed on
the command line. Export happens before Compose starts and once per rotation;
requests never call AWS. Recreate containers to read a new snapshot.
"""

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote


def secret_files(document, db_user="parentcheck", db_name="parentcheck"):
    """Validate everything before writing; accept only the EC2 schema."""
    if not isinstance(document, dict) or set(document) != {
        "SECRET_KEY", "POSTGRES_PASSWORD", "GEMINI_API_KEY"
    }:
        raise ValueError("Secret must contain exactly SECRET_KEY, POSTGRES_PASSWORD, GEMINI_API_KEY")
    if any(
        not isinstance(value, str) or len(value) > 8192 or any(c in value for c in "\r\n\0")
        for value in document.values()
    ):
        raise ValueError("Invalid secret value")
    for name in ("SECRET_KEY", "POSTGRES_PASSWORD"):
        value = document[name]
        if len(value) < 32 or value.lower().startswith("change-me") or value == (
            "dev-only-key-not-for-production"
        ):
            raise ValueError(f"{name} requires a strong value (32+ characters)")
    if not all(re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,62}", s) for s in (db_user, db_name)):
        raise ValueError("Use simple PostgreSQL identifiers")
    password = document["POSTGRES_PASSWORD"]
    files = {
        "postgres_password": password,
        "secret_key": document["SECRET_KEY"],
        "gemini_api_key": document["GEMINI_API_KEY"],
        "database_url": (
            f"postgresql+psycopg2://{db_user}:{quote(password, safe='')}@db:5432/{db_name}"
        ),
    }
    if any(len(value.encode("utf-8")) > 16384 for value in files.values()):
        raise ValueError("Secret exceeds the mounted configuration size limit")
    return files


def fetch_document(secret_arn, region):
    # Restrict this host tool to temporary EC2 instance-role credentials. An
    # operator's long-lived access key or local AWS profile must not be used.
    import boto3
    from botocore.config import Config

    os.environ["AWS_EC2_METADATA_V1_DISABLED"] = "true"
    session = boto3.Session(region_name=region)
    credentials = session.get_credentials()
    if credentials is None or credentials.method != "iam-role":
        raise RuntimeError("An EC2 instance role is required")
    client = session.client("secretsmanager", config=Config(
        connect_timeout=3, read_timeout=5, retries={"max_attempts": 2},
    ))
    response = client.get_secret_value(SecretId=secret_arn, VersionStage="AWSCURRENT")
    return json.loads(response["SecretString"])


def write_snapshot(files, directory):
    """Publish a complete snapshot atomically; existing mounts keep old inodes.

    Parent is root-only (0700); individual files are readable (0444) so the
    non-root web UID can read its bind mounts. Compose file secrets do not
    implement uid/gid/mode remapping. Host users cannot traverse the parent.
    """
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = directory.lstat()
    if directory.is_symlink() or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise RuntimeError("Secret directory must be private and owned by the exporter")
    snapshot = Path(tempfile.mkdtemp(prefix="version-", dir=directory))
    for name, value in files.items():
        path = snapshot / name
        with path.open("x", encoding="utf-8") as output:
            output.write(value)
        path.chmod(0o444)
    link = directory / f".current-{snapshot.name}"
    link.symlink_to(snapshot.name, target_is_directory=True)
    os.replace(link, directory / "current")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secret-arn", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--directory", default="/run/parent-check")
    parser.add_argument("--db-user", default="parentcheck")
    parser.add_argument("--db-name", default="parentcheck")
    args = parser.parse_args(argv)
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run as root on the Linux EC2 host")
    if not Path(args.directory).resolve().is_relative_to(Path("/run")):
        parser.error("Secrets must be stored under /run (volatile host storage)")
    try:
        document = fetch_document(args.secret_arn, args.region)
        files = secret_files(document, args.db_user, args.db_name)
        write_snapshot(files, args.directory)
    except Exception as exc:
        print(f"Secret export failed ({type(exc).__name__}); containers must not restart.",
              file=sys.stderr)
        return 1
    print("Secret snapshot ready. Recreate containers to load it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
