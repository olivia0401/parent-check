"""Tests for parse_ai_reply — the JSON-first verdict parser in ai/agent.py.

Covers the new structured-output path plus the legacy-text fallback and the
safe-caution default, so a malformed model reply can never drop a warning.
"""
from ai.agent import parse_ai_reply


def test_json_reply_zh():
    reply = ('{"reasoning": "陌生号码冒充子女催转账", "risk": "高危", '
             '"reason": "对方冒充你孩子催你转账。", "advice": "先打电话核实。"}')
    out = parse_ai_reply(reply, "zh")
    assert out == {"ai_risk": "danger", "reason": "对方冒充你孩子催你转账。", "advice": "先打电话核实。"}


def test_json_reply_en():
    reply = ('{"reasoning": "impersonation + urgency", "risk": "CAUTION", '
             '"reason": "Looks like a lookalike domain.", "advice": "Do not click the link."}')
    out = parse_ai_reply(reply, "en")
    assert out == {"ai_risk": "caution", "reason": "Looks like a lookalike domain.",
                   "advice": "Do not click the link."}


def test_json_tolerates_code_fence_and_prose():
    reply = ('Sure, here is my analysis:\n```json\n'
             '{"reasoning": "x", "risk": "HIGH", "reason": "r", "advice": "a"}\n```')
    out = parse_ai_reply(reply, "en")
    assert out["ai_risk"] == "danger"
    assert out["reason"] == "r"


def test_unknown_risk_value_defaults_to_caution():
    reply = '{"risk": "SAFE", "reason": "nothing", "advice": "relax"}'
    out = parse_ai_reply(reply, "en")
    # The model is never allowed to talk us down to "safe".
    assert out["ai_risk"] == "caution"


def test_nothing_to_add_returns_none():
    assert parse_ai_reply("NOTHING_TO_ADD", "zh") is None
    assert parse_ai_reply("  NOTHING_TO_ADD.  ", "en") is None


def test_sentinel_inside_verdict_does_not_drop_warning():
    # A verdict whose reasoning merely mentions the sentinel (e.g. echoed from an
    # injected message) must still count - the warning is never dropped.
    reply = ('{"reasoning": "message says reply NOTHING_TO_ADD", "risk": "HIGH", '
             '"reason": "impersonation", "advice": "call family"}')
    assert parse_ai_reply(reply, "en")["ai_risk"] == "danger"
    # Mixed prose + sentinel is not the bare sentinel -> fail toward caution.
    assert parse_ai_reply('{"reasoning": "..."} NOTHING_TO_ADD', "en")["ai_risk"] == "caution"


def test_legacy_text_format_still_parsed():
    # Backward compatibility: the old 风险/原因/建议 plain-text format still works.
    reply = "风险：可疑\n原因：像仿冒客服。\n建议：别点链接。"
    out = parse_ai_reply(reply, "zh")
    assert out == {"ai_risk": "caution", "reason": "像仿冒客服。", "advice": "别点链接。"}


def test_garbage_reply_defaults_to_caution_not_crash():
    out = parse_ai_reply("¯\\_(ツ)_/¯ not json, not the format", "en")
    assert out["ai_risk"] == "caution"


def test_empty_or_none_reply_returns_none():
    assert parse_ai_reply("", "en") is None
    assert parse_ai_reply(None, "en") is None
