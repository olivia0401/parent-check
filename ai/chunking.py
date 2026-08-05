"""
Split a long document into overlapping passages for indexing.

The scam knowledge base originally stored one embedding per case, which is fine
for short SMS-length messages but loses recall once we start ingesting longer
documents: a multi-paragraph scam letter, a health-product leaflet, or the text
OCR'd out of an uploaded screenshot (see ocr.py). Chunking splits such text into
passages small enough to embed precisely, with a little overlap so a scam signal
that straddles a boundary still lands whole in at least one chunk.

Pure and dependency-free: `chunk_text` is a deterministic function of its inputs,
so it is easy to unit-test and safe to run on the request path.
"""

DEFAULT_MAX_CHARS = 500
DEFAULT_OVERLAP = 80

# Boundary characters we prefer to cut on, so a passage doesn't end mid-sentence
# (CJK + Latin sentence enders, newline, space). Ordered doesn't matter — we take
# the latest one in the window.
_BOUNDARIES = "。！？!?\n. "


def chunk_text(text, max_chars=DEFAULT_MAX_CHARS, overlap=DEFAULT_OVERLAP):
    """Split `text` into overlapping passages of at most ~`max_chars` characters.

    A sliding window walks the text; each window's end is snapped back to the
    nearest sentence/space boundary (when that doesn't shrink the passage below
    half `max_chars`), so passages break on natural boundaries instead of mid-word.
    Consecutive passages share up to `overlap` characters of context.

    Returns `[text]` unchanged when it already fits, and `[]` for empty input.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    overlap = min(overlap, max_chars // 2)

    chunks = []
    start, n = 0, len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            window = text[start:end]
            boundary = max(window.rfind(ch) for ch in _BOUNDARIES)
            # Only snap if the boundary keeps the passage reasonably full.
            if boundary > max_chars // 2:
                end = start + boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        # Step back by `overlap` so the next passage re-includes some context.
        start = max(end - overlap, start + 1)
    return chunks
