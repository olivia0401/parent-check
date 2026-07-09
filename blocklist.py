# Checks links and phone numbers in a message against known scam patterns.
# High precision, no model needed - every hit points at an exact link/number.
# The lists below are small samples; a real product would feed these from a
# live threat-intel source instead.

import re

# A link that scores danger points if matched.
URL_RE = re.compile(r"(?:https?://|www\.)[^\s，。、！？；）)]+", re.IGNORECASE)

# Link shorteners (hide the real destination).
SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "t.cn",
    "goo.gl",
    "ow.ly",
    "is.gd",
    "buff.ly",
    "rebrand.ly",
    "cutt.ly",
    "t.co",
    "rb.gy",
}

# TLDs disproportionately used by scams / very cheap to register.
BAD_TLDS = {
    "xyz",
    "top",
    "icu",
    "click",
    "live",
    "vip",
    "buzz",
    "cn",
    "ru",
    "tk",
    "gq",
    "ml",
    "cf",
    "rest",
    "monster",
    "sbs",
    "cyou",
}

# Tiny sample of known-bad domains. Replace/extend with a real feed.
SAMPLE_BLOCKLIST = {
    "royalmail-redelivery.com",
    "hmrc-refund.net",
    "secure-verify-account.com",
}

# UK premium-rate (09) and personal (070) number shapes — costly call-back bait.
PREMIUM_PHONE_RE = re.compile(r"\b0(?:9\d{2}|70\d)\s?\d{3}\s?\d{3,4}\b")


def _host(url):
    """Extract the host part of a URL (no scheme, no www., no path)."""
    u = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
    u = re.sub(r"^www\.", "", u, flags=re.IGNORECASE)
    host = u.split("/")[0].split("?")[0].lower()
    return host.strip(" .,;:!?'\"()[]")


def check(content):
    """Inspect links and numbers in `content`.

    Returns (danger_points, reasons) where reasons are the exact offending
    tokens, shown to the user as language-neutral evidence.
    """
    danger = 0
    reasons = []
    seen = set()

    for url in URL_RE.findall(content):
        host = _host(url)
        bad = (
            re.match(r"\d{1,3}(?:\.\d{1,3}){3}$", host)  # raw IP address
            or host in SHORTENERS
            or host in SAMPLE_BLOCKLIST
            or host.startswith("xn--")
            or ".xn--" in host  # punycode look-alike
            or host.rsplit(".", 1)[-1] in BAD_TLDS
        )
        if bad and host not in seen:
            seen.add(host)
            danger += 3
            reasons.append(host)

    for match in PREMIUM_PHONE_RE.findall(content):
        token = match.strip()
        if token not in seen:
            seen.add(token)
            danger += 2
            reasons.append(token)

    return danger, reasons
