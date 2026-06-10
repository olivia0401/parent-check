"""
Very small "RAG" (retrieval) helper.

Instead of using a vector database, we just store each scam example in
SQLite together with its embedding (saved as a JSON list of numbers).
To find similar cases we load all rows for the language and compare
each one with cosine similarity. This is fine for a few dozen examples
- it would be too slow for a huge dataset, but we don't have one.
"""
import json
import math
import sqlite3
import time
from contextlib import closing


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    len_a = math.sqrt(sum(x * x for x in a))
    len_b = math.sqrt(sum(x * x for x in b))
    if len_a == 0 or len_b == 0:
        return 0.0
    return dot / (len_a * len_b)


class ScamRAGEngine:
    """Looks up similar scam examples for one language (zh or en)."""

    def __init__(self, db_path, llm_client, lang):
        self.db_path = db_path
        self.llm = llm_client
        self.lang = lang

    def seed_if_empty(self, json_path):
        """
        The first time the app runs, the scam_cases table is empty for
        this language, so load some starter examples from a JSON file
        and save them (with embeddings) to the database.

        If there are already rows for this language, do nothing.
        Returns how many cases were added.
        """
        if not self.llm.available:
            return 0

        with closing(self._db()) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM scam_cases WHERE lang = ?", (self.lang,)
            ).fetchone()[0]
        if count > 0:
            return 0

        try:
            with open(json_path, encoding="utf-8") as f:
                cases = json.load(f)
        except Exception:
            return 0

        added = 0
        for case in cases:
            embedding = self.llm.embed(case["text"])
            if embedding is None:
                continue
            with closing(self._db()) as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO scam_cases
                       (id, lang, text, category, analysis, embedding, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        case["id"],
                        self.lang,
                        case["text"],
                        case["category"],
                        case["analysis"],
                        json.dumps(embedding),
                        time.strftime("%Y-%m-%d %H:%M"),
                    ),
                )
                conn.commit()
            added += 1
        return added

    def retrieve_similar(self, text, n=3):
        """Return the n most similar saved scam cases for this text."""
        query_embedding = self.llm.embed(text)
        if query_embedding is None:
            return []

        with closing(self._db()) as conn:
            rows = conn.execute(
                "SELECT text, category, analysis, embedding FROM scam_cases WHERE lang = ?",
                (self.lang,),
            ).fetchall()

        if not rows:
            return []

        scored = []
        for row in rows:
            try:
                embedding = json.loads(row["embedding"])
                score = cosine_similarity(query_embedding, embedding)
                scored.append((score, row["text"], row["category"], row["analysis"]))
            except Exception:
                continue

        # best match first
        scored.sort(reverse=True)

        results = []
        for score, case_text, category, analysis in scored[:n]:
            results.append({
                "text": case_text,
                "category": category,
                "analysis": analysis,
                "similarity": round(score, 3),
            })
        return results

    def add_case(self, text, category, analysis):
        """Save a newly confirmed scam example for future lookups."""
        embedding = self.llm.embed(text)
        if embedding is None:
            return False
        case_id = f"{self.lang}_{int(time.time() * 1000)}"
        with closing(self._db()) as conn:
            conn.execute(
                """INSERT INTO scam_cases
                   (id, lang, text, category, analysis, embedding, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id, self.lang, text, category, analysis,
                    json.dumps(embedding), time.strftime("%Y-%m-%d %H:%M"),
                ),
            )
            conn.commit()
        return True

    def _db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
