# normalize.py
# Clean up text before keyword matching, so simple evasions still get caught.
#
# Scammers space out or punctuate sensitive words to dodge filters, e.g.
# "验 证 码", "验.证.码", "B A N K".  We fold everything to a compact form:
#   - full-width characters -> half-width
#   - lower-case
#   - a few known evasion variants mapped to their canonical word
#   - strip everything except letters, digits and Chinese characters
# Matching is then done on this compact form for both the text and the keyword.

import re

# Keep only ASCII letters/digits and CJK ideographs.
_KEEP = re.compile(r"[^0-9a-z一-鿿]")

# A deliberately small, low-false-positive list of known evasion variants.
# Extend this as real evasions are observed in the wild.
VARIANTS = {
    "yzm": "验证码",  # pinyin initials for 验证码 (verification code)
    "zhuanzhang": "转账",  # pinyin for 转账 (transfer money)
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
