"""
Downloads a web page (or WeChat article) the user pasted a link to, and
pulls out the readable text so it can be run through the scam checker.

If anything goes wrong (bad url, timeout, blocked address, etc.) this
returns {"ok": False, "error": "..."} instead of raising, so the route
in app.py can just show a friendly message.
"""
import re
from urllib.parse import urlparse

import requests

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

MAX_CHARS = 3000
TIMEOUT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en-GB,en;q=0.8",
}

# Don't fetch local/internal addresses - just block the common ones.
BLOCKED_HOSTS = (
    "localhost", "127.", "0.0.0.0", "::1",
    "10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "169.254.", "metadata.google.internal",
)


def is_url(text):
    """Check if the pasted text looks like a web link."""
    return bool(re.match(r"^https?://\S+", text.strip(), re.IGNORECASE))


def is_safe_url(url):
    """Make sure the link isn't pointing at a local/internal address."""
    try:
        host = urlparse(url.strip()).hostname or ""
        host = host.lower()
        for blocked in BLOCKED_HOSTS:
            if host == blocked.rstrip(".") or host.startswith(blocked):
                return False
        return True
    except Exception:
        return False


def extract_text(html, url):
    """Pull the main readable text out of a page's HTML."""
    if not HAS_BS4:
        # No BeautifulSoup available - just strip tags out with a regex
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]

    soup = BeautifulSoup(html, "html.parser")

    # Remove the bits of the page we don't care about
    for tag in soup(["script", "style", "nav", "header", "footer",
                     "aside", "iframe", "noscript", "figure"]):
        tag.decompose()

    # WeChat articles keep their content in a div with id="js_content"
    if "mp.weixin.qq.com" in url:
        block = soup.find(id="js_content")
        if block:
            return block.get_text(separator=" ", strip=True)[:MAX_CHARS]

    # For other pages, try a few common containers, then fall back to <body>
    for selector in ("article", "main", "[role='main']", ".article-content",
                     ".post-content", ".entry-content", "body"):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text[:MAX_CHARS]

    return soup.get_text(separator=" ", strip=True)[:MAX_CHARS]


def fetch_article(url):
    """
    Download the page at `url` and return its text.

    Returns either:
      {"ok": True, "text": "...", "title": "..."}
      {"ok": False, "error": "unsafe_url" / "timeout" / "no_content" / "fetch_failed"}
    """
    url = url.strip()

    if not is_safe_url(url):
        return {"ok": False, "error": "unsafe_url"}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"

        text = extract_text(resp.text, url)
        if len(text) < 50:
            return {"ok": False, "error": "no_content"}

        title = ""
        if HAS_BS4:
            soup = BeautifulSoup(resp.text, "html.parser")
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)[:120]

        return {"ok": True, "text": text, "title": title}

    except requests.Timeout:
        return {"ok": False, "error": "timeout"}
    except Exception:
        return {"ok": False, "error": "fetch_failed"}
