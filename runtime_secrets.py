"""Read explicitly mounted secrets once, before DB/client initialization.

EC2 Compose uses *_FILE; ECS and Render can still inject environment values.
No AWS credentials or Secrets Manager access are needed inside the containers.
"""

import os
from pathlib import Path

SECRET_NAMES = (
    "SECRET_KEY", "DATABASE_URL", "GEMINI_API_KEY",
    "AZURE_OPENAI_API_KEY", "AZURE_DOC_INTEL_KEY",
)


def is_production():
    return (
        os.environ.get("APP_ENV", "").strip().lower() == "production"
        or bool(os.environ.get("RENDER"))
    )


def load_secret_files(environ=None):
    """Fail closed on missing files or ambiguous sources; never echo values."""
    env = os.environ if environ is None else environ
    values = {}
    for name in SECRET_NAMES:
        path = env.get(f"{name}_FILE")
        if not path:
            continue
        if name in env:
            raise RuntimeError(f"Configure only {name} or {name}_FILE")
        try:
            with Path(path).open("rb") as secret_file:
                value = secret_file.read(16385)
            if len(value) > 16384:
                raise ValueError
            value = value.decode("utf-8").rstrip("\r\n")
            if "\x00" in value or (not value and name in {"SECRET_KEY", "DATABASE_URL"}):
                raise ValueError
        except (OSError, UnicodeError, ValueError):
            raise RuntimeError(f"Cannot load {name}_FILE") from None
        values[name] = value
    env.update(values)


def validate_session_key(value):
    if not value or len(value) < 32 or value.lower().startswith("change-me") or value == (
        "dev-only-key-not-for-production"
    ):
        raise RuntimeError("SECRET_KEY must be set to a strong value in production (32+ characters)")
