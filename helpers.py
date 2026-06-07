# helpers.py
# The "brain" of the app: turn a piece of text into a conservative risk judgement,
# and turn that judgement into a message the user can forward to their family.
#
# analyze_content() returns language-NEUTRAL codes (risk + category + the matched
# keywords). The actual words shown to the user are looked up later in
# translations.py, so the same saved check can be displayed in Chinese or English.
#
# The logic is deliberately rule-based, not AI. In a high-stakes setting (scams,
# medication) an explainable, predictable rule is safer than a clever black box:
# we can always tell the user exactly WHY we flagged something. That is a design
# choice, documented in the README.

import re

import blocklist
import semantic
from keywords import CRITICAL, SCAM, HEALTH
from normalize import compact, to_halfwidth

# Risk levels (codes). We never have a "safe" level — only degrees of caution.
RISK_OK = "ok"
RISK_CAUTION = "caution"
RISK_DANGER = "danger"

_CJK = re.compile(r"[一-鿿]")


def _find(terms, compact_text, spaced_text):
    """Return the terms that match.

    Two strategies, because the two languages behave differently:
      - Chinese terms: substring match on the COMPACT text, so spaced-out /
        full-width evasions like "验 证 码" are still caught.
      - English terms: WORD-BOUNDARY match on the lower-cased text, so short
        words like "pin" don't falsely fire inside "shopping" or "click" inside
        "clickbait".
    """
    found = []
    for t in terms:
        if _CJK.search(t):
            if compact(t) in compact_text:
                found.append(t)
        else:
            pattern = r"(?<![a-z0-9])" + re.escape(t.lower()) + r"(?![a-z0-9])"
            if re.search(pattern, spaced_text):
                found.append(t)
    return found


def analyze_content(content, source=""):
    """Score content and return language-neutral codes.

    Scoring (Week 3 algorithmic thinking):
        critical term  -> danger += 3
        scam term      -> danger += 2
        health term    -> caution += 1
        if source is a suspicious message AND we already have a signal -> danger += 1

    Returns a dict with:
        risk     -> "ok" | "caution" | "danger"
        category -> "none" | "scam" | "health" | "mixed"  (chooses the advice set)
        reasons  -> the matched keywords (evidence, shown as-is)
    """
    ctext = compact(content)
    stext = to_halfwidth(content).lower()
    hit_critical = _find(CRITICAL, ctext, stext)
    hit_scam = _find(SCAM, ctext, stext)
    hit_health = _find(HEALTH, ctext, stext)

    # Deterministic threat-intelligence floor: suspicious links / numbers.
    bl_danger, bl_reasons = blocklist.check(content)

    # Semantic escalation layer: catches keyword-free scams (e.g. impersonation).
    # It can only ADD danger, never reduce it.
    sem_danger, sem_reasons = semantic.escalate(content)

    danger = 3 * len(hit_critical) + 2 * len(hit_scam) + bl_danger + sem_danger
    caution = len(hit_health)

    # Use the context the user gave us: a "suspicious message" nudges danger up,
    # but only when there is already a signal, so we never alarm on a benign note
    # just because of the dropdown choice.
    if source == "suspicious_msg" and danger > 0:
        danger += 1

    # Verdict.
    if danger >= 3:
        risk = RISK_DANGER
    elif caution >= 1 or danger >= 1:
        risk = RISK_CAUTION
    else:
        risk = RISK_OK

    # Category decides which plain-language advice set to show.
    is_scam = bool(hit_critical or hit_scam or bl_reasons or sem_reasons)
    is_health = bool(hit_health)
    if risk == RISK_OK:
        category = "none"
    elif is_scam and not is_health:
        category = "scam"
    elif is_health and not is_scam:
        category = "health"
    elif is_scam and risk == RISK_DANGER:
        category = "scam"
    else:
        category = "mixed"

    # Combine evidence from all layers, de-duplicated, order preserved.
    reasons = list(
        dict.fromkeys(hit_critical + hit_scam + hit_health + bl_reasons + sem_reasons)
    )
    return {"risk": risk, "category": category, "reasons": reasons}


def generate_child_message(t, risk, category, reasons, source):
    """Build a ready-to-forward family message in the language of `t`.

    This is the core feature: it turns a moment of doubt into a conversation
    with family, instead of a lonely yes/no decision.
    """
    src_label = t["sources"].get(source, t["child_generic_src"])
    lines = [t["child_intro"].format(src=src_label)]
    lines.append("")
    lines.append(t["child_verdict"].format(risk=t["risk"][risk]))
    if reasons:
        lines.append("")
        lines.append(t["child_reason"].format(reasons=t["reason_sep"].join(reasons)))
    lines.append("")
    lines.append(t["child_advice"])
    return "\n".join(lines)


def build_view(t, risk, category, reasons, source):
    """Turn stored codes into displayable text for the current language `t`.

    Used by both the result page and the history-detail page, so a saved check
    can be rendered in whichever language the user is currently viewing.
    """
    # Translate any non-evidence reason codes (e.g. the model sentinel).
    display = [t["reason_model"] if r == "model" else r for r in reasons]
    summary = t["summary"][category]
    advice = t["advice"][category]
    child_message = generate_child_message(t, risk, category, display, source)
    return {
        "summary": summary,
        "advice": advice,
        "child_message": child_message,
        "reasons": display,
    }
