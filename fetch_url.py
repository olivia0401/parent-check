"""Bounded article retrieval: validated IP pinning, TLS hostname checks and deadlines."""

import concurrent.futures
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup

HAS_BS4 = True
MAX_CHARS = 3000
TIMEOUT = 12
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
_DNS_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="article-dns")
_DNS_SLOTS = threading.BoundedSemaphore(4)
HEADERS = {
    "User-Agent": "ParentCheck/1.0",
    "Accept": "text/html,text/plain,application/xhtml+xml",
    "Accept-Encoding": "identity",
    "Connection": "close",
}


class UnsafeURL(ValueError):
    pass


def is_url(text):
    return bool(re.match(r"^https?://\S+", text.strip(), re.IGNORECASE))


def _ip_is_internal(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return True
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return not address.is_global or address.is_multicast


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


def _resolve_target(url, deadline):
    if len(url) > 5000 or any(ord(c) <= 32 or c == "\\" for c in url):
        raise UnsafeURL
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafeURL
    host = (parsed.hostname or "").rstrip(".").encode("idna").decode().lower()
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host or port not in {80, 443} or host == "localhost" or host.endswith(".localhost"):
        raise UnsafeURL
    if not _DNS_SLOTS.acquire(blocking=False):
        raise TimeoutError
    try:
        future = _DNS_POOL.submit(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM)
    except Exception:
        _DNS_SLOTS.release()
        raise
    future.add_done_callback(lambda _future: _DNS_SLOTS.release())
    try:
        addresses = future.result(timeout=_remaining(deadline))
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError from None
    _remaining(deadline)
    if not addresses or any(_ip_is_internal(info[4][0]) for info in addresses):
        raise UnsafeURL
    # The selected numeric address is used directly by the actual TCP socket.
    return parsed, host, port, addresses[0][0], addresses[0][4][0]


def is_safe_url(url):
    try:
        _resolve_target(url.strip(), time.monotonic() + TIMEOUT)
        return True
    except Exception:
        return False


class _DeadlineHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, *args, deadline, **kwargs):
        self._deadline = deadline
        super().__init__(*args, **kwargs)

    def connect(self):
        http.client.HTTPConnection.connect(self)
        self.sock.settimeout(_remaining(self._deadline))
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)


def _pinned_connection(target, deadline):
    parsed, host, port, family, address = target
    timeout = min(3, _remaining(deadline))
    if parsed.scheme == "https":
        conn = _DeadlineHTTPSConnection(
            host, port, timeout=timeout, context=ssl.create_default_context(), deadline=deadline
        )
    else:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)

    def connect_numeric(_address, timeout=timeout, source_address=None, **_kwargs):
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.settimeout(min(timeout, _remaining(deadline)))
        try:
            # No second DNS lookup. HTTPSConnection still verifies/SNIs `host`.
            sock.connect((address, port))
            return sock
        except BaseException:
            sock.close()
            raise

    conn._create_connection = connect_numeric
    return conn


def _fetch_hop(target, deadline):
    parsed = target[0]
    conn = _pinned_connection(target, deadline)
    watchdog_socket = None
    timer = None
    expired = threading.Event()
    try:
        conn.connect()
        conn.sock.settimeout(_remaining(deadline))
        # Hold the socket even if HTTPConnection detaches it after headers.
        # SSLSocket cannot be dup()'d; its makefile reader retains the live FD.
        watchdog_socket = conn.sock

        def expire():
            expired.set()
            try:
                if isinstance(watchdog_socket, ssl.SSLSocket):
                    # Bypass the TLS wrapper's closed-state check: a response
                    # file may still own the FD after HTTPConnection.close().
                    socket.socket.shutdown(watchdog_socket, socket.SHUT_RDWR)
                else:
                    watchdog_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        timer = threading.Timer(_remaining(deadline), expire)
        timer.daemon = True
        timer.start()
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parsed.query:
            path += "?" + quote(parsed.query, safe="/%?:@!$&'()*+,;=-._~")
        conn.request("GET", path, headers=HEADERS)
        response = conn.getresponse()
        location = response.getheader("Location")
        if response.status in {301, 302, 303, 307, 308} and location:
            _remaining(deadline)
            return location, ""
        if not 200 <= response.status < 300:
            raise ValueError("http_status")
        content_type = response.getheader("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
            raise ValueError("content_type")
        # Refuse compressed responses even if the server ignores identity;
        # compressed bombs never reach a decompressor in this path.
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise ValueError("content_encoding")
        length = response.getheader("Content-Length")
        if length is not None and (int(length) < 0 or int(length) > MAX_BYTES):
            raise ValueError("body_size")
        body = bytearray()
        while True:
            _remaining(deadline)
            chunk = response.read1(min(8192, MAX_BYTES + 1 - len(body)))
            _remaining(deadline)
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError("body_size")
        if length is not None and len(body) != int(length):
            raise ValueError("incomplete_body")
        charset = response.headers.get_content_charset() or "utf-8"
        try:
            html = body.decode(charset, errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")
        return None, html
    except Exception:
        if expired.is_set():
            raise TimeoutError from None
        raise
    finally:
        if timer is not None:
            timer.cancel()
        if watchdog_socket is not None:
            watchdog_socket.close()
        conn.close()


def extract_text(html, url):
    """Pull the main readable text out of a page's HTML."""
    if not HAS_BS4:
        # No BeautifulSoup available - just strip tags out with a regex
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]

    soup = BeautifulSoup(html, "html.parser")

    # Remove the bits of the page we don't care about
    for tag in soup(
        ["script", "style", "nav", "header", "footer", "aside", "iframe", "noscript", "figure"]
    ):
        tag.decompose()

    # WeChat articles keep their content in a div with id="js_content"
    if urlparse(url).hostname == "mp.weixin.qq.com":
        block = soup.find(id="js_content")
        if block:
            return block.get_text(separator=" ", strip=True)[:MAX_CHARS]

    # For other pages, try a few common containers, then fall back to <body>
    for selector in (
        "article",
        "main",
        "[role='main']",
        ".article-content",
        ".post-content",
        ".entry-content",
        "body",
    ):
        el = soup.select_one(selector)
        if el:
            text = el.get_text(separator=" ", strip=True)
            if len(text) > 150:
                return text[:MAX_CHARS]

    return soup.get_text(separator=" ", strip=True)[:MAX_CHARS]


def fetch_article(url):
    """Fetch bounded HTML and retain every URL as deterministic risk evidence."""
    deadline = time.monotonic() + TIMEOUT
    urls = []
    try:
        url = url.strip()
        for _ in range(MAX_REDIRECTS + 1):
            target = _resolve_target(url, deadline)
            urls.append(url)
            location, html = _fetch_hop(target, deadline)
            if location is not None:
                url = urljoin(url, location)
                continue
            text = extract_text(html, url)
            _remaining(deadline)
            if len(text) < 50:
                return {"ok": False, "error": "no_content"}
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(strip=True)[:120] if soup.title else ""
            _remaining(deadline)
            return {"ok": True, "text": text, "title": title, "urls": urls}
        return {"ok": False, "error": "fetch_failed"}
    except UnsafeURL:
        return {"ok": False, "error": "unsafe_url"}
    except TimeoutError:
        return {"ok": False, "error": "timeout"}
    except Exception:
        return {"ok": False, "error": "fetch_failed"}
