"""
Retrieval over scam cases, backed by pgvector.

Previously this loaded every row for a language and computed cosine similarity
in Python (fine for a few dozen rows, too slow at scale). Now embeddings live in
a native `vector` column and similarity search is an indexed
`ORDER BY embedding <=> :query` executed in Postgres, so it scales to large
knowledge bases without changing this interface.
"""
import logging
import os
import time

from sqlalchemy import func, select

from db import ScamCase, SessionLocal

log = logging.getLogger(__name__)

# Cases whose cosine similarity to the query falls below this floor are dropped,
# so structurally-unrelated examples are never fed to the agent as "similar
# scams". Tunable via env; set to 0 to disable the filter (old behaviour).
DEFAULT_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.3"))


class ScamRAGEngine:
    """Looks up similar scam examples for one language (zh or en)."""

    def __init__(self, llm_client, lang):
        self.llm = llm_client
        self.lang = lang

    def seed_if_empty(self, json_path):
        """Load starter examples (with embeddings) the first time this language's
        knowledge base is empty. Returns how many cases were added."""
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
                embedding = self.llm.embed(case["text"])
                if embedding is None:
                    continue
                # merge = insert-or-ignore on the primary key
                s.merge(
                    ScamCase(
                        id=case["id"],
                        lang=self.lang,
                        text=case["text"],
                        category=case["category"],
                        analysis=case["analysis"],
                        embedding=embedding,
                    )
                )
                added += 1
        return added

    def retrieve_similar(self, text, n=3, min_similarity=None):
        """Return up to n saved scam cases most similar to this text, using an
        indexed cosine-distance search in Postgres. Cases scoring below
        `min_similarity` (default from RAG_MIN_SIMILARITY) are dropped, so a
        query with no genuinely-similar case returns nothing rather than the
        top-n irrelevant rows."""
        if min_similarity is None:
            min_similarity = DEFAULT_MIN_SIMILARITY
        query_embedding = self.llm.embed(text)
        if query_embedding is None:
            return []

        with SessionLocal() as s:
            rows = s.execute(
                select(
                    ScamCase.text,
                    ScamCase.category,
                    ScamCase.analysis,
                    ScamCase.embedding.cosine_distance(query_embedding).label("dist"),
                )
                .where(ScamCase.lang == self.lang)
                .order_by("dist")
                .limit(n)
            ).all()

        results = [
            {
                "text": r.text,
                "category": r.category,
                "analysis": r.analysis,
                # cosine distance -> similarity for a stable, human-readable score
                "similarity": round(1 - r.dist, 3),
            }
            for r in rows
            if (1 - r.dist) >= min_similarity
        ]
        if rows and not results:
            log.debug(
                "RAG: %d candidate(s) all below min_similarity=%.2f for %r",
                len(rows), min_similarity, text[:40],
            )
        return results

    def add_case(self, text, category, analysis):
        """Save a newly confirmed scam example for future lookups."""
        embedding = self.llm.embed(text)
        if embedding is None:
            return False
        case_id = f"{self.lang}_{int(time.time() * 1000)}"
        with SessionLocal.begin() as s:
            s.add(
                ScamCase(
                    id=case_id,
                    lang=self.lang,
                    text=text,
                    category=category,
                    analysis=analysis,
                    embedding=embedding,
                )
            )
        return True
