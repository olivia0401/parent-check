"""
Tools the AI is allowed to call while it analyses a message.

  query_knowledge_base - search our small list of past scam examples
  check_phone_numbers   - find phone numbers in the message and guess
                          what type each one is

Gemini decides for itself whether and when to call these - we just
describe them below and run whatever it asks for.
"""

import concurrent.futures
import logging
import re
from threading import BoundedSemaphore

from regions import current_region_code

logger = logging.getLogger(__name__)
MAX_TOOL_CALLS = 8
_TOOL_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="analysis-tool"
)
_TOOL_SLOTS = BoundedSemaphore(8)

# Deadline for one batch of parallel tool calls (seconds).
TOOL_TIMEOUT_S = 8

TOOL_DECLARATIONS = [
    {
        "name": "query_knowledge_base",
        "description": (
            "Search the scam case knowledge base for similar known scams. "
            "Use this to find cases that structurally or semantically match "
            "the message being analysed. Optionally pass a category to restrict "
            "the search to one scam type."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The message or key phrase to search for similar scam cases.",
                },
                "category": {
                    "type": "string",
                    "description": (
                        "Optional scam-type label to filter the search by "
                        "(metadata filter), e.g. only look up impersonation cases."
                    ),
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "check_phone_numbers",
        "description": (
            "Extract all phone numbers from the message and classify each one "
            "(e.g. international, premium-rate, domestic mobile). "
            "Use this whenever the message contains or references a phone number."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The full message text to extract phone numbers from.",
                }
            },
            "required": ["text"],
        },
    },
]


def execute_query_rag(text, rag, lang, category=None):
    """Look up similar scam cases and turn them into a short summary for the AI.

    `category`, when the model supplies it, narrows the search to one scam type
    (metadata filtering)."""
    cases = rag.retrieve_similar(text, n=3, category=category)
    if not cases:
        if lang == "zh":
            return {"found": False, "summary": "知识库中未找到类似案例。"}
        return {"found": False, "summary": "No similar cases found in the knowledge base."}

    lines = []
    for i, c in enumerate(cases, 1):
        preview = c["text"][:60] + ("..." if len(c["text"]) > 60 else "")
        if lang == "zh":
            lines.append(f"{i}. 类型：{c['category']} | 示例：{preview} | 分析：{c['analysis']}")
        else:
            lines.append(
                f"{i}. Type: {c['category']} | Example: {preview} | Analysis: {c['analysis']}"
            )

    header = (
        "知识库中找到以下类似骗局案例："
        if lang == "zh"
        else "Similar scam cases found in knowledge base:"
    )
    return {"found": True, "cases": len(cases), "summary": header + "\n" + "\n".join(lines)}


# Standalone short official numbers, per region (not part of a longer number).
_HELPLINE_RE = {
    "uk": r"(?<![\d+])(999|101|111|159)(?!\d)",
    "cn": r"(?<![\d+])(110|120|119|96110|12110)(?!\d)",
}


def execute_check_phone(text, lang, region=None):
    """Find phone numbers in the text and label what type each one looks like."""
    region = region or current_region_code()
    raw_matches = re.findall(r"(?<!\d)(\+?[\d][\d\s\-\(\)]{5,18}\d)(?!\d)", text)
    # Short official helplines (999 / 159 / 110 / 96110 ...) are too short for the
    # general pattern above, so pick them up explicitly as standalone numbers.
    raw_matches += re.findall(_HELPLINE_RE[region], text)

    # clean up spaces/dashes/brackets and drop duplicates
    phones = []
    for match in raw_matches:
        cleaned = re.sub(r"[\s\-\(\)]", "", match)
        if cleaned not in phones:
            phones.append(cleaned)

    if not phones:
        msg = "消息中未发现电话号码。" if lang == "zh" else "No phone numbers found in the message."
        return {"found": False, "summary": msg}

    classified = [{"number": p, "type": classify_phone(p, lang, region)} for p in phones]

    if lang == "zh":
        lines = ["发现以下电话号码："]
        for c in classified:
            lines.append(f"- {c['number']}（{c['type']}）")
    else:
        lines = ["Phone numbers found:"]
        for c in classified:
            lines.append(f"- {c['number']} ({c['type']})")

    return {"found": True, "numbers": classified, "summary": "\n".join(lines)}


def classify_phone(phone, lang, region=None):
    """Region selects numbering rules; language only selects the wording."""
    region = region or current_region_code()
    zh = lang == "zh"

    def label(chinese, english):
        return chinese if zh else english

    prefix = "+86" if region == "cn" else "+44"
    if phone.startswith("+") and not phone.startswith(prefix):
        return label(
            "境外号码（非中国大陆）" if region == "cn" else "境外号码（非英国）",
            "international number (not China)"
            if region == "cn"
            else "international number (not UK)",
        )
    if region == "cn":
        if re.fullmatch(r"(?:110|120|119|96110|12110)", phone):
            return label("官方热线号码", "China official helpline")
        if re.fullmatch(r"(?:\+?86)?1[3-9]\d{9}", phone):
            return label("中国大陆手机号", "China mobile")
        if phone.startswith("400"):
            return label("400客服号（可被仿冒）", "China service number (can be spoofed)")
        if phone.startswith(("+86", "86")):
            return label("中国大陆号码", "China number")
    else:
        if phone in {"999", "101", "111", "159"}:
            return label("英国官方热线号码", "UK official helpline")
        if re.match(r"^09\d{2}", phone):
            return label("英国高收费号码", "premium rate number")
        if phone.startswith(("0800", "+44800")):
            return label("英国免费电话", "UK freephone")
        if phone.startswith(("07", "+447")):
            return label("英国手机号", "UK mobile")
        if phone.startswith(("01", "02")):
            return label("英国固定电话", "UK landline")
    return label("未知类型号码", "unknown number type")


def run_tools_parallel(calls, rag, lang, original_text):
    """Bounded shared workers; exactly one ordered response per invocation."""

    def run_one(call):
        try:
            args = call.get("args", {})
            if not isinstance(args, dict):
                return {"error": "invalid_tool_arguments"}
            text = args.get("text", original_text)
            category = args.get("category")
            if (
                not isinstance(text, str)
                or len(text) > 5000
                or (category is not None and (not isinstance(category, str) or len(category) > 64))
            ):
                return {"error": "invalid_tool_arguments"}
            if call["name"] == "query_knowledge_base":
                return execute_query_rag(text, rag, lang, category)
            if call["name"] == "check_phone_numbers":
                return execute_check_phone(text, lang)
            return {"error": "tool_not_allowed"}
        except Exception as exc:
            logger.warning("Tool failed: %s", type(exc).__name__)
            return {"error": "tool_failed"}

    pending = {}
    responses = [None] * len(calls)
    for index, call in enumerate(calls):
        name = call.get("name", "unknown") if isinstance(call, dict) else "unknown"
        responses[index] = {"name": name, "response": {"error": "tool_busy"}}
        if isinstance(call, dict) and isinstance(call.get("id"), str):
            responses[index]["id"] = call["id"]
        if index >= MAX_TOOL_CALLS or not _TOOL_SLOTS.acquire(blocking=False):
            continue
        try:
            future = _TOOL_POOL.submit(run_one, call)
        except Exception:
            _TOOL_SLOTS.release()
            raise
        future.add_done_callback(lambda _future: _TOOL_SLOTS.release())
        pending[future] = index
    done, unfinished = concurrent.futures.wait(pending, timeout=TOOL_TIMEOUT_S)
    for future in done:
        try:
            responses[pending[future]]["response"] = future.result()
        except Exception:
            responses[pending[future]]["response"] = {"error": "tool_failed"}
    for future in unfinished:
        future.cancel()
        responses[pending[future]]["response"] = {"error": "timeout"}
    return responses
