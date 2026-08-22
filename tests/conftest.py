"""Test-only environment setup; production always uses DATABASE_URL."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
