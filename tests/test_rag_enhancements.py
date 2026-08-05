# Tests for the RAG retrieval pipeline enhancements: chunking, reranking, and
# metadata filtering. None of these need a database or an API key — chunking and
# reranking are pure functions, and the metadata-filter / chunk-index wiring is
# checked with fakes.

from ai import tools
from ai.chunking import chunk_text
from ai.rag_engine import ScamRAGEngine
from ai.rerank import fuse_score, lexical_overlap, rerank

# --- chunking ---------------------------------------------------------------

def test_chunk_short_text_is_single_chunk():
    assert chunk_text("a short scam message") == ["a short scam message"]


def test_chunk_empty_is_empty():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_long_text_splits_with_overlap():
    text = ". ".join(f"sentence number {i} here" for i in range(60))
    chunks = chunk_text(text, max_chars=200, overlap=40)
    assert len(chunks) > 1
    # every chunk respects the cap (allowing the small snap-to-boundary slack)
    assert all(len(c) <= 200 for c in chunks)
    # overlap means the whole document is still covered
    assert "sentence number 0" in chunks[0]
    assert "sentence number 59" in chunks[-1]


def test_chunk_hard_splits_text_with_no_boundaries():
    text = "x" * 1000
    chunks = chunk_text(text, max_chars=100, overlap=20)
    assert len(chunks) >= 10
    assert all(len(c) <= 100 for c in chunks)


# --- reranking --------------------------------------------------------------

def test_lexical_overlap_bounds():
    assert lexical_overlap("", "anything") == 0.0
    assert lexical_overlap("pay the fee now", "pay the fee now") == 1.0
    assert 0.0 < lexical_overlap("pay the parcel fee", "your parcel is held") < 1.0


def test_rerank_promotes_lexically_matching_case():
    query = "Royal Mail parcel fee, pay at this link"
    # 'b' has a slightly lower vector score but shares the query's exact tokens;
    # the fusion reranker should lift it above the generic 'a'.
    candidates = [
        {"text": "You have won a prize, claim your reward", "similarity": 0.72},
        {"text": "Royal Mail: your parcel is held, pay the fee at a link", "similarity": 0.70},
    ]
    ranked = rerank(query, candidates)
    assert ranked[0]["text"].startswith("Royal Mail")
    assert "rerank_score" in ranked[0]


def test_rerank_is_deterministic_and_pure():
    query = "verification code transfer"
    candidates = [
        {"text": "share your verification code and transfer", "similarity": 0.6},
        {"text": "the weather is nice today", "similarity": 0.61},
    ]
    before = [dict(c) for c in candidates]
    first = rerank(query, candidates)
    second = rerank(query, candidates)
    assert [c["text"] for c in first] == [c["text"] for c in second]
    assert candidates == before  # input not mutated


def test_rerank_empty():
    assert rerank("q", []) == []


def test_fuse_score_weights_similarity_and_overlap():
    # identical overlap -> the one with higher vector similarity wins
    high = fuse_score(0.9, "abc def", "abc def")
    low = fuse_score(0.1, "abc def", "abc def")
    assert high > low


# --- metadata filtering wiring ---------------------------------------------

class _FakeRag:
    """Captures the kwargs retrieve_similar is called with."""

    def __init__(self):
        self.calls = []

    def retrieve_similar(self, text, n=3, category=None):
        self.calls.append({"text": text, "n": n, "category": category})
        return []


def test_query_tool_threads_category_through():
    rag = _FakeRag()
    tools.execute_query_rag("some message", rag, "en", category="impersonation")
    assert rag.calls[0]["category"] == "impersonation"


def test_query_tool_defaults_category_to_none():
    rag = _FakeRag()
    tools.execute_query_rag("some message", rag, "en")
    assert rag.calls[0]["category"] is None


def test_run_tools_parallel_passes_category_arg():
    rag = _FakeRag()
    calls = [{"name": "query_knowledge_base", "args": {"text": "hi", "category": "refund"}}]
    tools.run_tools_parallel(calls, rag, "en", "original text")
    assert rag.calls[0]["category"] == "refund"


# --- chunking wiring in the index path -------------------------------------

class _FakeSession:
    def __init__(self):
        self.merged = []

    def merge(self, row):
        self.merged.append(row)


class _FakeLLM:
    available = True

    def embed(self, text):
        return [0.0] * 768


def test_index_case_single_row_for_short_text():
    engine = ScamRAGEngine(_FakeLLM(), "en")
    s = _FakeSession()
    written = engine._index_case(s, "en_1", "short scam", "refund", "explanation")
    assert written == 1
    assert s.merged[0].parent_id is None
    assert s.merged[0].chunk_index == 0
    assert s.merged[0].id == "en_1"


def test_index_case_chunks_long_text_with_parent_id():
    engine = ScamRAGEngine(_FakeLLM(), "en")
    s = _FakeSession()
    long_text = ". ".join(f"sentence {i} about a fake refund scam" for i in range(80))
    written = engine._index_case(s, "en_2", long_text, "refund", "explanation")
    assert written > 1
    assert all(row.parent_id == "en_2" for row in s.merged)
    assert [row.chunk_index for row in s.merged] == list(range(written))
    assert s.merged[1].id == "en_2#c1"
