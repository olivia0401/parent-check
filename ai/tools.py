"""
Tools the AI is allowed to call while it analyses a message.

  query_knowledge_base - search our small list of past scam examples
  check_phone_numbers   - find phone numbers in the message and guess
                          what type each one is

Gemini decides for itself whether and when to call these - we just
describe them below and run whatever it asks for.
"""
import re
import concurrent.futures


TOOL_DECLARATIONS = [
    {
        "name": "query_knowledge_base",
        "description": (
            "Search the scam case knowledge base for similar known scams. "
            "Use this to find cases that structurally or semantically match "
            "the message being analysed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The message or key phrase to search for similar scam cases.",
                }
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


def execute_query_rag(text, rag, lang):
    """Look up similar scam cases and turn them into a short summary for the AI."""
    cases = rag.retrieve_similar(text, n=3)
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
            lines.append(f"{i}. Type: {c['category']} | Example: {preview} | Analysis: {c['analysis']}")

    header = "知识库中找到以下类似骗局案例：" if lang == "zh" else "Similar scam cases found in knowledge base:"
    return {"found": True, "cases": len(cases), "summary": header + "\n" + "\n".join(lines)}


def execute_check_phone(text, lang):
    """Find phone numbers in the text and label what type each one looks like."""
    raw_matches = re.findall(r'(?<!\d)(\+?[\d][\d\s\-\(\)]{5,18}\d)(?!\d)', text)

    # clean up spaces/dashes/brackets and drop duplicates
    phones = []
    for match in raw_matches:
        cleaned = re.sub(r'[\s\-\(\)]', '', match)
        if cleaned not in phones:
            phones.append(cleaned)

    if not phones:
        msg = "消息中未发现电话号码。" if lang == "zh" else "No phone numbers found in the message."
        return {"found": False, "summary": msg}

    classified = [{"number": p, "type": classify_phone(p, lang)} for p in phones]

    if lang == "zh":
        lines = ["发现以下电话号码："]
        for c in classified:
            lines.append(f"- {c['number']}（{c['type']}）")
    else:
        lines = ["Phone numbers found:"]
        for c in classified:
            lines.append(f"- {c['number']} ({c['type']})")

    return {"found": True, "numbers": classified, "summary": "\n".join(lines)}


def classify_phone(phone, lang):
    """Guess what kind of number this is, based on a few simple patterns."""
    if lang == "zh":
        if phone.startswith('+') and not phone.startswith('+86'):
            return "境外号码（非中国大陆）"
        if re.match(r'^400', phone):
            return "400客服号（可被仿冒）"
        if re.match(r'^\+?86?1[3-9]\d{9}$', phone):
            return "中国大陆手机号"
        if re.match(r'^(110|120|119|96110|12110)$', phone):
            return "官方热线号码"
        if re.match(r'^\+?86', phone):
            return "中国大陆号码"
        if len(phone) <= 6:
            return "短号码（可能是官方热线）"
        return "未知类型号码"
    else:
        if re.match(r'^09\d{2}', phone):
            return "premium rate number"
        if phone.startswith('+') and not phone.startswith('+44'):
            return "international number (not UK)"
        if re.match(r'^0800|^\+44800', phone):
            return "UK freephone"
        if re.match(r'^07|^\+447', phone):
            return "UK mobile"
        if re.match(r'^01|^02', phone):
            return "UK landline"
        if re.match(r'^(999|101|111|159)$', phone):
            return "UK official helpline"
        return "unknown number type"


def run_tools_parallel(calls, rag, lang, original_text):
    """
    Run all the tool calls Gemini asked for at the same time (instead of
    one after another), so the whole check doesn't take too long.
    Returns a list of {"name": ..., "response": ...} dicts.
    """
    def run_one(call):
        name = call["name"]
        args = call.get("args", {})
        text = args.get("text", original_text)
        try:
            if name == "query_knowledge_base":
                result = execute_query_rag(text, rag, lang)
            elif name == "check_phone_numbers":
                result = execute_check_phone(text, lang)
            else:
                result = {"error": f"Unknown tool: {name}"}
        except Exception as e:
            result = {"error": str(e)}
        return {"name": name, "response": result}

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(run_one, c) for c in calls]
        for f in concurrent.futures.as_completed(futures, timeout=8):
            try:
                results.append(f.result())
            except Exception:
                pass
    return results
