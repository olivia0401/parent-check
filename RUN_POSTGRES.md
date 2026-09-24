# Running Parent Check on PostgreSQL + pgvector

The data layer moved from SQLite (with embeddings stored as JSON and cosine
computed in Python) to **PostgreSQL + pgvector**, so scam-case retrieval is now
a native, indexed nearest-neighbour query. Redis backs the shared rate limiter
(`ratelimit.py`), with an in-process fallback when it is unreachable.

## 1. Run the whole stack locally

```bash
docker compose up --build
```

This starts:

- **db** — `pgvector/pgvector:pg16` (Postgres with the `vector` extension)
- **redis** — `redis:7-alpine`
- **web** — the Flask app (gunicorn) on http://localhost:8000

On first boot the app runs `db.init_db()`, which:
1. `CREATE EXTENSION IF NOT EXISTS vector`
2. creates the `checks` and `scam_cases` tables
3. creates the HNSW cosine index on `scam_cases.embedding`

If `GEMINI_API_KEY` is set, the zh/en knowledge bases seed themselves from
`data/scams_*.json` on first run.

## 2. Run the app against Postgres without Docker

```bash
# start just Postgres + Redis
docker compose up -d db redis

pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://parentcheck:parentcheck@localhost:5432/parentcheck
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
python app.py
```

## 3. Migrations (Alembic)

`db.init_db()` is enough to boot. Alembic is configured for schema **changes**
(config in `alembic.ini`, wiring in `migrations/env.py` — it reads `DATABASE_URL`
and autogenerates against the models in `db.py`), but no revision has been
committed yet (`migrations/versions/` is empty).

To create the initial migration:

```bash
export DATABASE_URL=postgresql+psycopg2://parentcheck:parentcheck@localhost:5432/parentcheck
alembic revision --autogenerate -m "initial schema"
```

Then, in the generated file under `migrations/versions/`, make sure the
extension is created **before** the tables (autogenerate does not emit this):

```python
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # ... op.create_table(...) etc.
```

Apply it:

```bash
alembic upgrade head
```

For an existing DB already created by `init_db()`, baseline it instead so
Alembic doesn't try to recreate the tables:

```bash
alembic stamp head
```

## Notes

- The old SQLite path has been removed; a leftover local `parent_check.db` is
  unused (and gitignored).
- `EMBED_DIM = 768` in `db.py` matches the 768-dim vectors requested from Gemini
  `gemini-embedding-001` (`ai/llm_client.py`). If you change the embedding model
  or dimension, change both and generate a new migration.
