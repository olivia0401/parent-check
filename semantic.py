# Escalation layer - looks at combinations of signals instead of single
# keywords, so it can catch things like family impersonation:
#   "Mum, I changed my number, send me some money quickly."
# None of those words alone is a scam keyword, but together they are.
#
# Can only ADD danger, never reduce it - the keyword rules + blocklist stay the
# floor. _model_escalate() below is the same idea but with a trained classifier,
# off unless SEMANTIC_MODEL is set.

import os

from normalize import compact

# matched on the compact form so spacing/full-width/case don't matter
_NUMBER_CHANGE = [
    "新号码",
    "新号",
    "换了号",
    "换号",
    "new number",
    "this is my new number",
]
_MONEY = [
    "打钱",
    "打一点",
    "打点",
    "汇钱",
    "汇款",
    "转账",
    "转钱",
    "借钱",
    "付钱",
    "急用钱",
    "send money",
    "transfer",
    "help pay",
    "pay a bill",
    "wire",
]
_FAMILY = [
    "妈",
    "爸",
    "儿子",
    "女儿",
    "孙子",
    "孙女",
    "hi mum",
    "hi dad",
    "grandma",
    "grandpa",
    "grandson",
    "granddaughter",
]
_URGENCY = ["急", "赶紧", "马上", "尽快", "quickly", "urgent", "asap"]


def escalate(content):
    """Return (extra_danger, reasons). Can only raise risk, never lower it."""
    c = compact(content)

    def hits(terms):
        return [t for t in terms if compact(t) in c]

    nc, money, fam, urg = (
        hits(_NUMBER_CHANGE),
        hits(_MONEY),
        hits(_FAMILY),
        hits(_URGENCY),
    )

    extra = 0
    reasons = []

    # "new number + money" or "family + money + urgency" - either combo reads
    # as an impersonation/emergency-money scam even with no scam keywords
    if (nc and money) or (fam and money and urg):
        extra += 3
        reasons = list(dict.fromkeys(nc + money + fam + urg))

    m_extra, m_reasons = _model_escalate(content)
    return extra + m_extra, reasons + m_reasons


# trained by train_model.py - kept high so it only adds confidence, not noise
_MODEL_THRESHOLD = 0.90
_model_cache = {"loaded": False, "pipe": None}


def _load_model():
    """Lazy-load the saved classifier once. Any failure just means no model."""
    if _model_cache["loaded"]:
        return _model_cache["pipe"]
    _model_cache["loaded"] = True
    try:
        import joblib  # lazy import so the web app doesn't need ML deps

        path = os.path.join(os.path.dirname(__file__), "model", "scam_model.joblib")
        _model_cache["pipe"] = joblib.load(path)
    except Exception:
        _model_cache["pipe"] = None
    return _model_cache["pipe"]


def _model_escalate(content):
    """Optional ML layer, off unless SEMANTIC_MODEL is set. Same contract as
    escalate(): can only raise risk, and any error here is swallowed so it
    can't break the rule-based result."""
    if not os.environ.get("SEMANTIC_MODEL"):
        return 0, []
    pipe = _load_model()
    if pipe is None:
        return 0, []
    try:
        prob = pipe.predict_proba([content])[0][1]  # P(scam)
        if prob >= _MODEL_THRESHOLD:
            return 2, ["model"]  # "model" is translated for display
    except Exception:
        return 0, []
    return 0, []
