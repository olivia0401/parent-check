# Unit tests for the OCR layer (ocr.extract_text). Pure and deterministic: no
# network, no API key, no database, no app import. A tiny fake LLM stands in for
# the Gemini-vision backend, so these run everywhere - locally and in CI - and
# nail down the decision logic that guards the image path (mime allow-list, size
# cap, "no text found" floor, engine selection, length trim).

import ocr


class _FakeLLM:
    """Stand-in for LLMClient: only the two attributes ocr.py touches."""

    def __init__(self, available=True, text="EXTRACTED"):
        self.available = available
        self._text = text
        self.calls = 0

    def read_image_text(self, image_bytes, mime_type):
        self.calls += 1
        return self._text


PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 100  # plausible non-empty image payload


def test_rejects_unsupported_mime():
    out = ocr.extract_text(PNG, "image/gif", _FakeLLM())
    assert out == {"ok": False, "error": "unsupported"}


def test_mime_is_case_insensitive():
    out = ocr.extract_text(PNG, "IMAGE/PNG", _FakeLLM(text="hello scam text"))
    assert out["ok"] is True


def test_empty_bytes_rejected_as_too_large():
    # falsy image_bytes takes the size-guard branch
    out = ocr.extract_text(b"", "image/png", _FakeLLM())
    assert out == {"ok": False, "error": "too_large"}


def test_oversized_rejected():
    big = b"x" * (ocr.MAX_BYTES + 1)
    out = ocr.extract_text(big, "image/png", _FakeLLM())
    assert out == {"ok": False, "error": "too_large"}


def test_no_llm_and_no_azure_fails_gracefully():
    out = ocr.extract_text(PNG, "image/png", None)
    assert out == {"ok": False, "error": "failed"}


def test_unavailable_llm_fails_gracefully():
    out = ocr.extract_text(PNG, "image/png", _FakeLLM(available=False))
    assert out == {"ok": False, "error": "failed"}


def test_successful_gemini_ocr():
    llm = _FakeLLM(text="  您的账户异常，请点击链接验证  ")
    out = ocr.extract_text(PNG, "image/png", llm)
    assert out["ok"] is True
    assert out["engine"] == "gemini"
    assert out["text"] == "您的账户异常，请点击链接验证"  # stripped
    assert llm.calls == 1


def test_too_little_text_is_no_text():
    # fewer readable chars than MIN_TEXT -> treated as "nothing to analyse"
    out = ocr.extract_text(PNG, "image/png", _FakeLLM(text="hi"))
    assert out == {"ok": False, "error": "no_text"}


def test_output_trimmed_to_max_chars():
    llm = _FakeLLM(text="a" * (ocr.MAX_CHARS + 500))
    out = ocr.extract_text(PNG, "image/png", llm)
    assert out["ok"] is True
    assert len(out["text"]) == ocr.MAX_CHARS


def test_llm_returning_none_fails():
    out = ocr.extract_text(PNG, "image/png", _FakeLLM(text=None))
    assert out == {"ok": False, "error": "failed"}
