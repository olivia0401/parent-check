"""
SQLAlchemy data layer for Parent Check.

Replaces the previous hand-rolled sqlite3 access (see the old get_db/init_db in
app.py and the JSON-embedding loop in ai/rag_engine.py). Business data now lives
in PostgreSQL, and scam-case embeddings use pgvector so similarity search runs
as a native, indexed query instead of loading every row and computing cosine in
Python.

Connection string comes from DATABASE_URL. The default points at the local
docker-compose Postgres; production sets DATABASE_URL (e.g. AWS RDS).
"""
import os
from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

try:
    from sqlalchemy.pool import StaticPool
except ImportError:  # pragma: no cover
    StaticPool = None

# Gemini text-embedding-004 returns 768-dim vectors. Keep in sync with the model.
EMBED_DIM = 768

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://parentcheck:parentcheck@localhost:5432/parentcheck",
)

# pool_pre_ping avoids "server closed the connection" errors after RDS idles out.
_engine_kwargs = {"pool_pre_ping": True, "future": True}
if DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if StaticPool is not None:
        _engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


class Base(DeclarativeBase):
    pass


class Check(Base):
    """One check the user ran. We never store the original submitted text -
    only the language-neutral verdict codes and matched evidence."""

    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    risk: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    reasons: Mapped[str] = mapped_column(Text, nullable=False, default="")
    helpful: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # anonymous per-browser id, so history stays private without accounts
    user_token: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)


class ScamCase(Base):
    """Scam-case knowledge base for RAG. `embedding` is a native pgvector column
    rather than a JSON string, so retrieval is an indexed nearest-neighbour query.

    A long document (e.g. text OCR'd from an uploaded screenshot) is split into
    overlapping passages before indexing, so one source case can span several rows.
    Those rows share a `parent_id` and carry their `chunk_index`; retrieval collapses
    them back to one hit per source case. A case that fits in a single chunk has
    `parent_id = NULL` and `chunk_index = 0`."""

    __tablename__ = "scam_cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lang: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    analysis: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBED_DIM), nullable=False)
    # Chunk metadata: NULL parent_id means the case wasn't split.
    parent_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


# HNSW index with cosine distance ops: turns retrieve_similar() into an ANN scan.
Index(
    "idx_scam_cases_embedding",
    ScamCase.embedding,
    postgresql_using="hnsw",
    postgresql_with={"m": 16, "ef_construction": 64},
    postgresql_ops={"embedding": "vector_cosine_ops"},
)


def init_db():
    """Enable pgvector and create tables/indexes. Idempotent - safe to call on
    every startup. Alembic owns schema changes in production (see RUN_POSTGRES.md);
    this is the zero-config path for local dev and first boot."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(engine)
    else:
        # Test-only SQLite path: history routes do not need pgvector/RAG.
        Check.__table__.create(engine, checkfirst=True)

    if engine.dialect.name != "postgresql":
        return
    # Backfill the chunk-metadata columns on a scam_cases table created before
    # chunking existed. ADD COLUMN IF NOT EXISTS keeps this idempotent, matching
    # the zero-config spirit of create_all above (Alembic owns prod migrations).
    with engine.begin() as conn:
        conn.execute(text(
            "ALTER TABLE scam_cases ADD COLUMN IF NOT EXISTS parent_id VARCHAR(64)"
        ))
        conn.execute(text(
            "ALTER TABLE scam_cases ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_scam_cases_parent_id ON scam_cases (parent_id)"
        ))
