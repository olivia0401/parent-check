"""Validate the migration's libpq SCRAM API against the disposable CI database."""

import os
import secrets
import uuid

import pytest


@pytest.mark.skipif(os.environ.get("GITHUB_ACTIONS") != "true", reason="Disposable CI PostgreSQL only")
def test_client_scram_verifier_authenticates_without_plaintext_in_sql():
    import psycopg2
    from psycopg2 import sql
    from psycopg2.extensions import encrypt_password, make_dsn

    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://", 1)
    role = "migration_test_" + uuid.uuid4().hex
    password = secrets.token_urlsafe(48)
    connection = psycopg2.connect(dsn, connect_timeout=5)
    connection.autocommit = True
    try:
        verifier = encrypt_password(password, role, connection, algorithm="scram-sha-256")
        assert verifier.startswith("SCRAM-SHA-256$") and password not in verifier
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role)),
                           (verifier,))
        try:
            with psycopg2.connect(make_dsn(dsn, user=role, password=password), connect_timeout=5) as fresh:
                with fresh.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    assert cursor.fetchone() == (1,)
        finally:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
    finally:
        connection.close()
