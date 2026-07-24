"""Langfuse tracing for the Gemini calls — off unless LANGFUSE_* env vars are set.

When it's on, each generate()/generate_with_tools() call is logged so I can see
the AI second-opinion layer call by call (prompt, reply, tokens, latency). It's
best-effort: anything failing here is swallowed, so a trace can't break a user's
scam check. Setup lives in requirements-qe.txt / README.
"""
import os

_client = None
_resolved = False


def enabled():
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")
                and os.environ.get("LANGFUSE_SECRET_KEY"))


def _client_or_none():
    # Build the client once. None = disabled, or the SDK isn't installed.
    global _client, _resolved
    if _resolved:
        return _client
    _resolved = True
    if enabled():
        try:
            import atexit
            from langfuse import get_client
            _client = get_client()
            atexit.register(flush)
        except Exception:
            _client = None
    return _client


def log_generation(name, prompt, output, *, model, latency_s=None,
                   usage=None, metadata=None):
    # usage is {"input_tokens": int, "output_tokens": int} when Gemini reports it.
    client = _client_or_none()
    if client is None:
        return
    try:
        gen = client.start_observation(name=name, as_type="generation")
        meta = dict(metadata or {})
        if latency_s is not None:
            meta["latency_s"] = round(latency_s, 3)
        kwargs = {"model": model, "input": prompt, "output": output, "metadata": meta}
        if usage:
            kwargs["usage_details"] = usage
        gen.update(**kwargs)
        gen.end()
    except Exception:
        pass


def flush():
    client = _client_or_none()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
