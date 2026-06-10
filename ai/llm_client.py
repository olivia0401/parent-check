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
import requests

GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
EMBED_URL = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"


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
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": 400,
                    },
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
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
        try:
            resp = requests.post(
                f"{GENERATE_URL}?key={self.api_key}",
                json={
                    "contents": messages,
                    "tools": [{"functionDeclarations": tools}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600},
                },
                timeout=20,
            )
            resp.raise_for_status()
            parts = resp.json()["candidates"][0]["content"].get("parts", [])

            func_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if func_calls:
                return {
                    "type": "function_calls",
                    "calls": [{"name": fc["name"], "args": fc.get("args", {})} for fc in func_calls],
                    "raw_parts": parts,
                }

            text = "".join(p.get("text", "") for p in parts if "text" in p)
            return {"type": "text", "text": text}
        except Exception:
            return None

    def embed(self, text):
        """Turn text into a 768-number vector for the RAG search (or None)."""
        if not self.available:
            return None
        try:
            resp = requests.post(
                f"{EMBED_URL}?key={self.api_key}",
                json={
                    "model": "models/text-embedding-004",
                    "content": {"parts": [{"text": text[:2000]}]},
                },
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
        except Exception:
            return None
