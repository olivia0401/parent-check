"""
Reads the text out of a screenshot the user uploaded (a photo of a suspicious
SMS, WeChat / WhatsApp message, email or health ad), so it can be run through
the exact same scam checker as pasted text or a fetched URL.

Two backends, tried in order — mirroring how the rest of the app treats AI as an
optional enhancement that degrades gracefully rather than a hard dependency:

  1. Azure Document Intelligence (prebuilt-read) — used only if
     AZURE_DOC_INTEL_ENDPOINT + AZURE_DOC_INTEL_KEY are set. This is the
     enterprise OCR path (high-volume docs, tables, handwriting, layout).
  2. Gemini vision — the default. Reuses the Gemini client the app already
     configures, so screenshot OCR works with no extra dependency or setup.

Like fetch_url.py, this never raises: it returns
  {"ok": True,  "text": "...", "engine": "azure"|"gemini"}
  {"ok": False, "error": "unsupported"|"too_large"|"no_text"|"failed"}
so the route in app.py can just show a friendly message.
"""
import os
import time

import requests

MAX_BYTES = 6 * 1024 * 1024  # 6 MB upload cap
ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MIN_TEXT = 6  # fewer readable chars than this -> treat as "no text found"
MAX_CHARS = 5000  # same cap the pipeline uses for pasted text


def extract_text(image_bytes, mime_type, llm=None):
    """OCR an uploaded screenshot and return its text (see module docstring)."""
    mime_type = (mime_type or "").lower()
    if mime_type not in ALLOWED_MIME:
        return {"ok": False, "error": "unsupported"}
    if not image_bytes or len(image_bytes) > MAX_BYTES:
        return {"ok": False, "error": "too_large"}

    # 1. Enterprise OCR backend, if configured. Falls through to Gemini on error.
    if os.environ.get("AZURE_DOC_INTEL_ENDPOINT") and os.environ.get("AZURE_DOC_INTEL_KEY"):
        text = _azure_read(image_bytes)
        if text is not None:
            return _finish(text, "azure")

    # 2. Default: Gemini vision (reuses the app's existing LLM client).
    if llm is not None and getattr(llm, "available", False):
        text = llm.read_image_text(image_bytes, mime_type)
        if text is not None:
            return _finish(text, "gemini")

    return {"ok": False, "error": "failed"}


def _finish(text, engine):
    """Trim and length-check the OCR output, matching the pasted-text cap."""
    text = (text or "").strip()
    if len(text) < MIN_TEXT:
        return {"ok": False, "error": "no_text"}
    return {"ok": True, "text": text[:MAX_CHARS], "engine": engine}


# --- Azure Document Intelligence (prebuilt-read) ----------------------------
AZURE_API_VERSION = "2024-11-30"
AZURE_POLL_TIMEOUT = 30  # seconds to wait for the async analysis to finish


def _azure_read(image_bytes):
    """
    Run Azure's prebuilt-read model over the image and return the extracted
    text, or None on any error (so the caller can fall back to Gemini).

    The REST API is asynchronous: the POST returns 202 + an Operation-Location
    URL, which we poll until the analysis reports "succeeded".
    """
    endpoint = os.environ["AZURE_DOC_INTEL_ENDPOINT"].rstrip("/")
    key = os.environ["AZURE_DOC_INTEL_KEY"]
    try:
        submit = requests.post(
            f"{endpoint}/documentintelligence/documentModels/prebuilt-read:analyze"
            f"?api-version={AZURE_API_VERSION}",
            headers={"Ocp-Apim-Subscription-Key": key,
                     "Content-Type": "application/octet-stream"},
            data=image_bytes, timeout=15,
        )
        submit.raise_for_status()
        op_url = submit.headers.get("Operation-Location")
        if not op_url:
            return None

        deadline = time.monotonic() + AZURE_POLL_TIMEOUT
        while time.monotonic() < deadline:
            poll = requests.get(
                op_url, headers={"Ocp-Apim-Subscription-Key": key}, timeout=10,
            )
            poll.raise_for_status()
            body = poll.json()
            status = body.get("status")
            if status == "succeeded":
                return body.get("analyzeResult", {}).get("content", "")
            if status == "failed":
                return None
            time.sleep(1)
        return None  # timed out waiting for the result
    except Exception:
        return None
