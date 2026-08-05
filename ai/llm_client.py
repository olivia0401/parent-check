"""
Small wrapper around the LLM API.

We just use plain `requests` calls here instead of the official SDKs, to keep
things simple and avoid extra dependencies on the free Render plan.

Two providers, selected by environment:

  * Google Gemini (default) — text generation, tool-calling, image OCR and
    embeddings, on the free tier.
  * Azure OpenAI (optional) — if AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY are
    set, embeddings and plain text generation route to Azure OpenAI instead, so
    the same app runs on a fully Azure AI stack (Azure OpenAI here + Azure
    Document Intelligence in ocr.py). Tool-calling and image OCR stay on Gemini.

Provider is fixed per deployment via env, which matters for embeddings: vectors
from different providers aren't comparable, so a knowledge base must be seeded
and queried with the same one.

If anything goes wrong (no API key, network error, bad response) every method
just returns None, so the rest of the app can carry on without the AI step.
"""
import base64
import os
import time

import requests

try:
    from . import llm_trace
except ImportError:
    import llm_trace

# Models refreshed 2026-07: the account's free tier gives 0 quota on
# gemini-2.0-flash and text-embedding-004 is retired. gemini-flash-lite-latest
# has free quota and supports function calling; gemini-embedding-001 replaces
# the retired embedding model.
GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"

# Embedding dimensionality. Must match the pgvector vector(768) column in db.py;
# both Gemini (outputDimensionality) and Azure text-embedding-3-* (dimensions)
# can emit 768-dim vectors, so the two stacks stay column-compatible.
EMBED_DIM = 768


def _usage(body):
    """Pull token counts out of Gemini's usageMetadata for tracing (or None)."""
    um = body.get("usageMetadata") if isinstance(body, dict) else None
    if not um:
        return None
    return {
        "input_tokens": um.get("promptTokenCount", 0),
        "output_tokens": um.get("candidatesTokenCount", 0),
    }


def _azure_usage(body):
    """Pull token counts out of Azure OpenAI's `usage` block for tracing (or None)."""
    u = body.get("usage") if isinstance(body, dict) else None
    if not u:
        return None
    return {
        "input_tokens": u.get("prompt_tokens", 0),
        "output_tokens": u.get("completion_tokens", 0),
    }


def _azure_openai_config():
    """Return the Azure OpenAI config from the environment, or None if it isn't
    configured. Read at call time so the provider can be toggled per deployment
    (and in tests) without reimporting."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    if not (endpoint and key):
        return None
    return {
        "endpoint": endpoint.rstrip("/"),
        "key": key,
        # deployment names as created in the Azure OpenAI resource
        "chat": os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o-mini"),
        "embed": os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small"),
        "api_version": os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    }


class LLMClient:
    """Talks to Gemini, or to Azure OpenAI when AZURE_OPENAI_* is configured.
    Disabled (every method returns None) if neither provider is set up."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")

    @property
    def available(self):
        """True if either provider can serve requests."""
        return bool(self.api_key) or _azure_openai_config() is not None

    def generate(self, prompt, temperature=0.3, trace_label="scam.generate"):
        """Send a plain text prompt and get back the text reply (or None).
        Routes to Azure OpenAI when configured, else Gemini. `trace_label` tags
        the observability span so distinct callers (e.g. the verifier agent) show
        up separately from generic generations."""
        if _azure_openai_config() is not None:
            return self._azure_generate(prompt, temperature, trace_label)
        if not self.api_key:
            return None
        t0 = time.monotonic()
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 400,
                        # flash-lite is a thinking model; disable thinking so the
                        # small output budget isn't spent before the answer.
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            llm_trace.log_generation(
                trace_label, prompt, text, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, usage=_usage(body),
            )
            return text
        except Exception:
            llm_trace.log_generation(
                trace_label, prompt, None, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, metadata={"error": True},
            )
            return None

    def generate_with_tools(self, messages, tools):
        """
        Same as generate(), but also tells Gemini which "tools" (functions)
        it is allowed to call if it wants more information first.

        Tool-calling stays on Gemini (its function-call format is what
        agent_graph.py speaks), so this needs a Gemini key even when embeddings
        and plain generation are served by Azure OpenAI.

        Returns one of:
          {"type": "text", "text": "..."}
          {"type": "function_calls", "calls": [{"name": ..., "args": ...}], "raw_parts": [...]}
        or None if the request fails.
        """
        if not self.api_key:
            return None
        t0 = time.monotonic()
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": messages,
                    "tools": [{"functionDeclarations": tools}],
                    # 800 (was 600): the verdict is now a JSON object whose first
                    # field is a step-by-step `reasoning`, so the reply is a bit
                    # longer. (Gemini rejects responseSchema/JSON-mode in the same
                    # request as functionDeclarations, so we ask for JSON in the
                    # prompt and parse leniently instead — see agent.parse_ai_reply.)
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 800, "thinkingConfig": {"thinkingBudget": 0}},
                },
                timeout=20,
            )
            resp.raise_for_status()
            body = resp.json()
            parts = body["candidates"][0]["content"].get("parts", [])

            func_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if func_calls:
                names = [fc["name"] for fc in func_calls]
                llm_trace.log_generation(
                    "scam.agent", messages, f"tool_calls: {names}",
                    model="gemini-flash-lite-latest", latency_s=time.monotonic() - t0,
                    usage=_usage(body), metadata={"kind": "function_calls"},
                )
                return {
                    "type": "function_calls",
                    "calls": [{"name": fc["name"], "args": fc.get("args", {})} for fc in func_calls],
                    "raw_parts": parts,
                }

            text = "".join(p.get("text", "") for p in parts if "text" in p)
            llm_trace.log_generation(
                "scam.agent", messages, text, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, usage=_usage(body),
                metadata={"kind": "text"},
            )
            return {"type": "text", "text": text}
        except Exception:
            llm_trace.log_generation(
                "scam.agent", messages, None, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, metadata={"error": True},
            )
            return None

    def read_image_text(self, image_bytes, mime_type):
        """
        OCR: read every piece of text visible in an image (a screenshot of a
        message, email or ad) and return it as plain text, in its original
        language. Returns None on failure or if no Gemini key is set, so ocr.py can
        fall back or show a friendly error.

        This is the Gemini-vision OCR path (the enterprise path in ocr.py is Azure
        Document Intelligence), so it needs a Gemini key specifically.

        Gemini Flash is multimodal, so this is just generate() with an extra
        inline-image part alongside the prompt - no new dependency needed.
        """
        if not self.api_key:
            return None
        t0 = time.monotonic()
        prompt = (
            "Extract ALL text visible in this image exactly as it appears, "
            "keeping the original language. Return only the raw text, with no "
            "commentary, labels or translation. If there is no text, return nothing."
        )
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": [{"parts": [
                        {"text": prompt},
                        {"inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(image_bytes).decode(),
                        }},
                    ]}],
                    # NB: no thinkingConfig here. Unlike the text endpoints, the
                    # multimodal (image) request rejects thinkingBudget=0 with a
                    # 400 "invalid argument", so we let the model use its default.
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 800,
                    },
                },
                timeout=30,
            )
            resp.raise_for_status()
            body = resp.json()
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            llm_trace.log_generation(
                "scam.ocr", "[image]", text, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, usage=_usage(body),
            )
            return text.strip()
        except Exception:
            llm_trace.log_generation(
                "scam.ocr", "[image]", None, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, metadata={"error": True},
            )
            return None

    def embed(self, text):
        """Turn text into an EMBED_DIM-length vector for the RAG search (or None).
        Routes to Azure OpenAI when configured, else Gemini."""
        if _azure_openai_config() is not None:
            return self._azure_embed(text)
        if not self.api_key:
            return None
        try:
            resp = requests.post(
                f"{EMBED_URL}?key={self.api_key}",
                json={
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": text[:2000]}]},
                    "outputDimensionality": EMBED_DIM,  # match the pgvector vector(768) column
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
        except Exception:
            return None

    # --- Azure OpenAI backend -----------------------------------------------
    # REST calls (api-key header, deployment in the path); same graceful-failure
    # contract as the Gemini methods above.

    def _azure_generate(self, prompt, temperature=0.3, trace_label="scam.generate"):
        """Text generation via an Azure OpenAI chat-completions deployment."""
        cfg = _azure_openai_config()
        if cfg is None:
            return None
        t0 = time.monotonic()
        url = (
            f"{cfg['endpoint']}/openai/deployments/{cfg['chat']}"
            f"/chat/completions?api-version={cfg['api_version']}"
        )
        try:
            resp = requests.post(
                url,
                headers={"api-key": cfg["key"]},
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": 400,
                },
                timeout=15,
            )
            resp.raise_for_status()
            body = resp.json()
            text = body["choices"][0]["message"]["content"]
            llm_trace.log_generation(
                trace_label, prompt, text, model=f"azure:{cfg['chat']}",
                latency_s=time.monotonic() - t0, usage=_azure_usage(body),
            )
            return text
        except Exception:
            llm_trace.log_generation(
                trace_label, prompt, None, model=f"azure:{cfg['chat']}",
                latency_s=time.monotonic() - t0, metadata={"error": True},
            )
            return None

    def _azure_embed(self, text):
        """Embeddings via an Azure OpenAI embeddings deployment. `dimensions`
        pins the vector to EMBED_DIM so it fits the pgvector column (needs a
        text-embedding-3-* deployment; ada-002 ignores the parameter)."""
        cfg = _azure_openai_config()
        if cfg is None:
            return None
        url = (
            f"{cfg['endpoint']}/openai/deployments/{cfg['embed']}"
            f"/embeddings?api-version={cfg['api_version']}"
        )
        try:
            resp = requests.post(
                url,
                headers={"api-key": cfg["key"]},
                json={"input": text[:2000], "dimensions": EMBED_DIM},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
        except Exception:
            return None
