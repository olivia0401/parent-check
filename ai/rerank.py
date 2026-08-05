"""
Second-stage reranking for RAG retrieval.

pgvector gives a fast but coarse first pass: approximate nearest neighbours by
embedding cosine similarity. Cosine alone can rank a vaguely on-topic case above
one that shares the scam's actual tell (a specific phrase, a lookalike domain),
because embeddings blur exact tokens together. So retrieve_similar() over-fetches
a candidate pool from pgvector and reranks it before handing the top few to the
agent.

The default reranker is dependency-free and deterministic: it fuses the vector
similarity with a lexical-overlap signal, so a candidate that both looks similar
AND shares concrete tokens with the query rises to the top. Setting
RERANK_CROSS_ENCODER (with sentence-transformers installed) swaps in a proper
cross-encoder; if that model can't load we fall back to the fusion reranker, in
keeping with the rest of the app treating heavier ML as an optional enhancement.
"""
import os
import re

# Weight the lexical-overlap signal gets relative to vector similarity when the
# two are fused into a single rerank score. Tunable via env.
LEX_WEIGHT = float(os.getenv("RERANK_LEX_WEIGHT", "0.35"))

# A token is a run of Latin letters/digits, or a single CJK character.
_TOKEN_RE = re.compile(r"[0-9a-z]+|[一-鿿]", re.IGNORECASE)


def _tokens(text):
    """Lowercased word tokens plus individual CJK characters, as a set."""
    return set(_TOKEN_RE.findall((text or "").lower()))


def lexical_overlap(query, text):
    """Fraction of the query's tokens that also appear in `text`, in [0, 1]."""
    q = _tokens(query)
    if not q:
        return 0.0
    return len(q & _tokens(text)) / len(q)


def fuse_score(similarity, query, text, lex_weight=LEX_WEIGHT):
    """Blend vector similarity with lexical overlap into one rerank score."""
    return (1 - lex_weight) * float(similarity) + lex_weight * lexical_overlap(query, text)


def rerank(query, candidates, top_n=None, lex_weight=LEX_WEIGHT):
    """
    Reorder retrieved candidates best-first and return the top_n.

    Each candidate is a dict with at least "text" and "similarity" (as produced by
    ScamRAGEngine.retrieve_similar). A cross-encoder is used if configured and
    importable; otherwise the deterministic vector+lexical fusion reranker runs.
    Returns a new list of copies (with a "rerank_score" added); input is not
    mutated. An index tiebreaker keeps the ordering stable and deterministic.
    """
    if not candidates:
        return []

    scores = _cross_encoder_scores(query, candidates)
    if scores is None:
        scores = [
            fuse_score(c.get("similarity", 0.0), query, c.get("text", ""), lex_weight)
            for c in candidates
        ]

    order = sorted(
        range(len(candidates)), key=lambda i: (-scores[i], i)
    )
    ordered = [dict(candidates[i], rerank_score=round(float(scores[i]), 4)) for i in order]
    return ordered[:top_n] if top_n else ordered


def _cross_encoder_scores(query, candidates):
    """Optional cross-encoder pass. Returns a list of scores aligned with
    `candidates`, or None if no cross-encoder is configured / it can't be loaded
    (so the caller falls back to the fusion reranker)."""
    model_name = os.getenv("RERANK_CROSS_ENCODER")
    if not model_name:
        return None
    model = _load_cross_encoder(model_name)
    if model is None:
        return None
    try:
        pairs = [(query, c.get("text", "")) for c in candidates]
        return [float(s) for s in model.predict(pairs)]
    except Exception:
        return None


_ce_cache = {"loaded": False, "model": None}


def _load_cross_encoder(model_name):
    """Lazy-load the cross-encoder once. Any failure just disables it."""
    if _ce_cache["loaded"]:
        return _ce_cache["model"]
    _ce_cache["loaded"] = True
    try:
        from sentence_transformers import CrossEncoder

        _ce_cache["model"] = CrossEncoder(model_name)
    except Exception:
        _ce_cache["model"] = None
    return _ce_cache["model"]
