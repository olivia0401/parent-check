"""
Retrieval over scam cases, backed by pgvector.

Previously this loaded every row for a language and computed cosine similarity
in Python (fine for a few dozen rows, too slow at scale). Now embeddings live in
a native `vector` column and similarity search is an indexed
`ORDER BY embedding <=> :query` executed in Postgres, so it scales to large
knowledge bases without changing this interface.

The retrieval pipeline is three stages:
  1. index-time chunking — long documents are split into overlapping passages
     (chunking.py), each stored as its own row tagged with parent_id/chunk_index;
  2. metadata filtering — retrieval can be narrowed to one scam `category`;
  3. rerank — pgvector over-fetches a candidate pool that is reranked
     (rerank.py) before the top-n cases are collapsed per source and returned.
"""
import logging
import os
import time

from sqlalchemy import func, select

from db import ScamCase, SessionLocal

from .chunking import chunk_text
from .rerank import rerank as rerank_candidates

log = logging.getLogger(__name__)

# Cases whose cosine similarity to the query falls below this floor are dropped,
# so structurally-unrelated examples are never fed to the agent as "similar
# scams". Tunable via env; set to 0 to disable the filter (old behaviour).
DEFAULT_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.3"))

# Long documents are split into passages of at most this many characters before
# indexing (see chunking.py). Short cases stay a single row.
CHUNK_MAX_CHARS = int(os.getenv("RAG_CHUNK_CHARS", "500"))

# When reranking, over-fetch this many times the requested n from pgvector, so
# the reranker has room to promote a match the ANN scan ranked slightly lower.
RERANK_POOL_MULT = int(os.getenv("RAG_RERANK_POOL_MULT", "4"))


def _rerank_enabled(flag):
    """Resolve whether to rerank: explicit arg wins, else RAG_RERANK (default on)."""
    if flag is not None:
        return flag
    return os.getenv("RAG_RERANK", "1") != "0"


class ScamRAGEngine:
    """Looks up similar scam examples for one language (zh or en)."""

    def __init__(self, llm_client, lang):
        self.llm = llm_client
        self.lang = lang

    def _index_case(self, session, base_id, text, category, analysis):
        """Embed a case and store it, splitting long text into overlapping
        passages (chunking) so each is indexed as its own row tagged with
        parent_id + chunk_index. A case that fits one chunk is stored as a single
        row with parent_id=None. Returns how many rows were written (chunks whose
        embedding call failed are skipped)."""
        chunks = chunk_text(text, max_chars=CHUNK_MAX_CHARS)
        if not chunks:
            return 0
        single = len(chunks) == 1
        written = 0
        for idx, chunk in enumerate(chunks):
            embedding = self.llm.embed(chunk)
            if embedding is None:
                continue
            # merge = insert-or-ignore on the primary key
            session.merge(
                ScamCase(
                    id=base_id if single else f"{base_id}#c{idx}",
                    lang=self.lang,
                    text=chunk,
                    category=category,
                    analysis=analysis,
                    parent_id=None if single else base_id,
                    chunk_index=idx,
                    embedding=embedding,
                )
            )
            written += 1
        return written

    def seed_if_empty(self, json_path):
        """Load starter examples (with embeddings) the first time this language's
        knowledge base is empty. Returns how many rows were added."""
        import json

        if not self.llm.available:
            return 0

        with SessionLocal() as s:
            count = s.scalar(
                select(func.count())
                .select_from(ScamCase)
                .where(ScamCase.lang == self.lang)
            )
        if count:
            return 0

        try:
            with open(json_path, encoding="utf-8") as f:
                cases = json.load(f)
        except Exception as e:
            log.warning("RAG seed skipped: could not load %s (%s)", json_path, e)
            return 0

        added = 0
        with SessionLocal.begin() as s:
            for case in cases:
                added += self._index_case(
                    s, case["id"], case["text"], case["category"], case["analysis"]
                )
        return added

    def retrieve_similar(self, text, n=3, min_similarity=None, category=None, rerank=None):
        """Return up to n saved scam cases most similar to this text.

        Stage 1 is an indexed cosine-distance search in Postgres, optionally
        narrowed to a single scam `category` (metadata filtering). Cases scoring
        below `min_similarity` (default from RAG_MIN_SIMILARITY) are dropped, so a
        query with no genuinely-similar case returns nothing rather than the top-n
        irrelevant rows. When reranking is on (default; RAG_RERANK=0 disables), a
        larger candidate pool is fetched and reordered by rerank.py before the
        results are collapsed to one hit per source case (chunks of the same
        document share a parent_id) and truncated to n."""
        if min_similarity is None:
            min_similarity = DEFAULT_MIN_SIMILARITY
        rerank = _rerank_enabled(rerank)
        query_embedding = self.llm.embed(text)
        if query_embedding is None:
            return []

        pool = max(n * RERANK_POOL_MULT, n) if rerank else n

        with SessionLocal() as s:
            stmt = (
                select(
                    ScamCase.text,
                    ScamCase.category,
                    ScamCase.analysis,
                    ScamCase.parent_id,
                    ScamCase.id,
                    ScamCase.embedding.cosine_distance(query_embedding).label("dist"),
                )
                .where(ScamCase.lang == self.lang)
            )
            if category:
                stmt = stmt.where(ScamCase.category == category)  # metadata filter
            rows = s.execute(stmt.order_by("dist").limit(pool)).all()

        candidates = [
            {
                "text": r.text,
                "category": r.category,
                "analysis": r.analysis,
                # a chunk's source case; a single-row case is its own parent
                "parent": r.parent_id or r.id,
                # cosine distance -> similarity for a stable, human-readable score
                "similarity": round(1 - r.dist, 3),
            }
            for r in rows
            if (1 - r.dist) >= min_similarity
        ]
        if not candidates:
            if rows:
                log.debug(
                    "RAG: %d candidate(s) all below min_similarity=%.2f for %r",
                    len(rows), min_similarity, text[:40],
                )
            return []

        if rerank:
            candidates = rerank_candidates(text, candidates)

        # Collapse chunks back to their source case: keep the best-ranked chunk
        # per parent so the agent sees distinct cases, not slices of one document.
        seen, deduped = set(), []
        for c in candidates:
            if c["parent"] in seen:
                continue
            seen.add(c["parent"])
            deduped.append(c)

        return [
            {k: c[k] for k in ("text", "category", "analysis", "similarity")}
            for c in deduped[:n]
        ]

    def add_case(self, text, category, analysis):
        """Save a newly confirmed scam example for future lookups (chunking long
        text into several indexed rows). Returns True if anything was stored."""
        base_id = f"{self.lang}_{int(time.time() * 1000)}"
        with SessionLocal.begin() as s:
            written = self._index_case(s, base_id, text, category, analysis)
        return written > 0
