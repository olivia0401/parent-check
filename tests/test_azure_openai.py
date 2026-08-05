# Tests for the optional Azure OpenAI provider in ai/llm_client.py. These check
# config detection and provider routing only — no network call is made (the
# actual _azure_* HTTP methods are monkeypatched), so they run in CI without any
# key. Provider selection is read from the environment at call time.

import ai.llm_client as llm_mod
from ai.llm_client import LLMClient


def _clear(monkeypatch):
    for k in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def _set_azure(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://res.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")


def test_azure_config_absent_by_default(monkeypatch):
    _clear(monkeypatch)
    assert llm_mod._azure_openai_config() is None


def test_azure_config_parsed_and_trims_endpoint(monkeypatch):
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    cfg = llm_mod._azure_openai_config()
    assert cfg["endpoint"] == "https://res.openai.azure.com"  # trailing slash stripped
    assert cfg["chat"] and cfg["embed"] and cfg["api_version"]


def test_deployment_names_are_overridable(monkeypatch):
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_EMBED_DEPLOYMENT", "my-embed")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "my-chat")
    cfg = llm_mod._azure_openai_config()
    assert cfg["embed"] == "my-embed"
    assert cfg["chat"] == "my-chat"


def test_available_true_with_azure_only(monkeypatch):
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    assert LLMClient().available is True  # no Gemini key, but Azure is configured


def test_unavailable_with_no_provider(monkeypatch):
    _clear(monkeypatch)
    assert LLMClient().available is False


def test_embed_routes_to_azure_when_configured(monkeypatch):
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    c = LLMClient()
    monkeypatch.setattr(c, "_azure_embed", lambda text: [0.5] * llm_mod.EMBED_DIM)
    out = c.embed("hello")
    assert out == [0.5] * llm_mod.EMBED_DIM


def test_generate_routes_to_azure_when_configured(monkeypatch):
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    c = LLMClient()
    monkeypatch.setattr(c, "_azure_generate", lambda prompt, temperature=0.3: "FROM_AZURE")
    assert c.generate("hi") == "FROM_AZURE"


def test_generate_and_embed_none_without_any_provider(monkeypatch):
    _clear(monkeypatch)
    c = LLMClient()
    assert c.generate("hi") is None
    assert c.embed("hi") is None


def test_tool_calling_requires_gemini_even_with_azure(monkeypatch):
    # Tool-calling stays on Gemini; with only Azure configured it returns None
    # (the agent then falls back to the rule-based verdict).
    _clear(monkeypatch)
    _set_azure(monkeypatch)
    c = LLMClient()
    assert c.generate_with_tools([], []) is None
