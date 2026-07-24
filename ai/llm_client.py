"""
Small wrapper around the Gemini API.

We just use plain `requests` calls here instead of the official Google
SDK, to keep things simple and avoid extra dependencies on the free
Render plan.

If anything goes wrong (no API key, network error, bad response) every
method just returns None, so the rest of the app can carry on without
the AI step.
"""
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


def _usage(body):
    """Pull token counts out of Gemini's usageMetadata for tracing (or None)."""
    um = body.get("usageMetadata") if isinstance(body, dict) else None
    if not um:
        return None
    return {
        "input_tokens": um.get("promptTokenCount", 0),
        "output_tokens": um.get("candidatesTokenCount", 0),
    }


class LLMClient:
    """Talks to the Gemini Flash free tier. Disabled if GEMINI_API_KEY is not set."""

    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")

    @property
    def available(self):
        return bool(self.api_key)

    def generate(self, prompt, temperature=0.3):
        """Send a plain text prompt and get back the text reply (or None)."""
        if not self.available:
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
                "scam.generate", prompt, text, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, usage=_usage(body),
            )
            return text
        except Exception:
            llm_trace.log_generation(
                "scam.generate", prompt, None, model="gemini-flash-lite-latest",
                latency_s=time.monotonic() - t0, metadata={"error": True},
            )
            return None

    def generate_with_tools(self, messages, tools):
        """
        Same as generate(), but also tells Gemini which "tools" (functions)
        it is allowed to call if it wants more information first.

        Returns one of:
          {"type": "text", "text": "..."}
          {"type": "function_calls", "calls": [{"name": ..., "args": ...}], "raw_parts": [...]}
        or None if the request fails.
        """
        if not self.available:
            return None
        t0 = time.monotonic()
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": messages,
                    "tools": [{"functionDeclarations": tools}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600, "thinkingConfig": {"thinkingBudget": 0}},
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

    def embed(self, text):
        """Turn text into a 768-number vector for the RAG search (or None)."""
        if not self.available:
            return None
        try:
            resp = requests.post(
                f"{EMBED_URL}?key={self.api_key}",
                json={
                    "model": "models/gemini-embedding-001",
                    "content": {"parts": [{"text": text[:2000]}]},
                    "outputDimensionality": 768,  # match the pgvector vector(768) column
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
        except Exception:
            return None
