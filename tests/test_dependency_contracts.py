import asyncio
import contextlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

from alembic import context
from alembic.config import Config
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def test_actual_alembic_environment_accepts_encoded_database_password(monkeypatch):
    # db has already loaded the test engine; only Alembic's URL is overridden.
    import db  # noqa: F401

    url = "postgresql+psycopg2://user:p%40ss%25word%2Fvalue@db/database"
    captured = {}
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setattr(context, "config", Config(), raising=False)
    monkeypatch.setattr(context, "is_offline_mode", lambda: True)
    monkeypatch.setattr(context, "configure", lambda **kwargs: captured.update(kwargs))
    monkeypatch.setattr(context, "begin_transaction", contextlib.nullcontext)
    monkeypatch.setattr(context, "run_migrations", lambda: None)
    runpy.run_path(str(ROOT / "migrations/env.py"))
    assert captured["url"] == url
    assert make_url(captured["url"]).password == "p@ss%word/value"


def test_mcp_entrypoint_can_import_after_a_real_dependency_install():
    process = subprocess.run(
        [sys.executable, "-c", "import mcp_server; assert mcp_server.mcp"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr


def test_real_mcp_stdio_session_lists_and_calls_the_registered_tool():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(ROOT / "mcp_server.py")],
            env={
                "PATH": os.environ.get("PATH", ""),
                "REGION": "uk",
                "DATABASE_URL": "sqlite:///:memory:",
            },
        )
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == {
                    "check_phone_numbers",
                    "query_knowledge_base",
                }
                response = await session.call_tool(
                    "check_phone_numbers", {"text": "Call 159", "lang": "zh"}
                )
                assert not response.isError
                result = json.loads(response.content[0].text)
                assert result["found"] and result["numbers"][0]["number"] == "159"

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))


def test_installed_database_instrumentation_actually_produces_a_span():
    code = """
from sqlalchemy import create_engine, text
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
exporter = InMemorySpanExporter()
provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
engine = create_engine('sqlite:///:memory:')
SQLAlchemyInstrumentor().instrument(engine=engine)
with engine.connect() as connection:
    connection.execute(text('SELECT 1'))
assert any('sqlalchemy' in span.instrumentation_scope.name for span in exporter.get_finished_spans())
"""
    environment = {key: value for key, value in os.environ.items() if not key.startswith("OTEL_")}
    process = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr
