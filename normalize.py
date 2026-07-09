# Cleans up text before keyword matching, so spacing/punctuation tricks like
# "验 证 码" or "B A N K" still get caught: full-width -> half-width, lowercase,
# a few known pinyin/abbreviation variants mapped back to the real word, then
# strip everything except letters, digits and Chinese characters. Both the text
# and the keywords get run through this before comparing.

import re

_KEEP = re.compile(r"[^0-9a-z一-鿿]")

# small list of known evasions seen in the wild, extend as needed
VARIANTS = {
    "yzm": "验证码",  # pinyin initials for "verification code"
    "zhuanzhang": "转账",  # pinyin for "transfer money"
}


def to_halfwidth(s):
    """Convert full-width (全角) characters to their half-width equivalents."""
    out = []
    for ch in s:
        code = ord(ch)
        if code == 0x3000:  # full-width space
            code = 0x20
        elif 0xFF01 <= code <= 0xFF5E:  # full-width ASCII range
            code -= 0xFEE0
        out.append(chr(code))
    return "".join(out)


def compact(text):
    """Return the compact, match-ready form of `text`."""
    if not text:
        return ""
    s = to_halfwidth(text).lower()
    for variant, canonical in VARIANTS.items():
        s = s.replace(variant, canonical)
    return _KEEP.sub("", s)
