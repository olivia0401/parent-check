"""Exercise the actual address pinning and bounded HTTP reader without external network access."""

import email.message
import socket
import ssl
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest

import fetch_url


def address(ip="93.184.216.34"):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 443))]


def test_tcp_uses_the_validated_ip_without_resolving_hostname_again(monkeypatch):
    resolutions = []

    def resolve(host, port, **kwargs):
        resolutions.append(host)
        return address() if len(resolutions) == 1 else address("127.0.0.1")

    connected = []

    class Socket:
        def settimeout(self, value):
            pass

        def setsockopt(self, *args):
            pass

        def connect(self, peer):
            connected.append(peer)

        def close(self):
            pass

    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", resolve)
    deadline = time.monotonic() + 2
    target = fetch_url._resolve_target("http://rebind.example/", deadline)
    monkeypatch.setattr(fetch_url.socket, "socket", lambda *args: Socket())
    connection = fetch_url._pinned_connection(target, deadline)
    connection.connect()
    connection.close()
    assert resolutions == ["rebind.example"]
    assert connected == [("93.184.216.34", 80)]


def test_https_keeps_certificate_validation_and_original_hostname():
    target = (urlparse("https://example.com/"), "example.com", 443, socket.AF_INET, "93.184.216.34")
    connection = fetch_url._pinned_connection(target, time.monotonic() + 2)
    assert connection.host == "example.com"
    assert connection._context.check_hostname is True
    assert connection._context.verify_mode == ssl.CERT_REQUIRED


def test_tls_handshake_uses_the_remaining_total_budget_and_original_sni(monkeypatch):
    from types import SimpleNamespace

    now = [0.0]
    peers = []
    wrapped = []

    class Socket:
        def settimeout(self, value):
            self.timeout = value

        def setsockopt(self, *args):
            pass

        def connect(self, peer):
            peers.append(peer)
            now[0] = 2.5

        def close(self):
            pass

    def wrap(sock, *, server_hostname):
        wrapped.append((server_hostname, sock.timeout))
        return sock

    monkeypatch.setattr(fetch_url.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(
        fetch_url.ssl, "create_default_context", lambda: SimpleNamespace(wrap_socket=wrap)
    )
    monkeypatch.setattr(fetch_url.socket, "socket", lambda *a: Socket())
    target = (urlparse("https://example.com/"), "example.com", 443, socket.AF_INET, "93.184.216.34")
    connection = fetch_url._pinned_connection(target, 3.0)
    connection.connect()
    assert peers == [("93.184.216.34", 443)]
    assert wrapped == [("example.com", 0.5)]
    connection.close()


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.64.0.1", "::1", "::ffff:127.0.0.1"]
)
def test_private_or_non_global_dns_answers_are_rejected(monkeypatch, ip):
    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", lambda *args, **kwargs: address(ip))
    assert not fetch_url.is_safe_url("https://example.com/")


def test_public_and_private_mixed_answers_are_rejected(monkeypatch):
    monkeypatch.setattr(
        fetch_url.socket, "getaddrinfo", lambda *a, **kw: address() + address("10.0.0.1")
    )
    assert not fetch_url.is_safe_url("https://example.com/")


def test_dns_time_is_in_the_total_deadline(monkeypatch):
    def slow_resolve(*args, **kwargs):
        time.sleep(0.15)
        return address()

    monkeypatch.setattr(fetch_url, "TIMEOUT", 0.02)
    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", slow_resolve)
    start = time.monotonic()
    assert fetch_url.fetch_article("https://example.com/")["error"] == "timeout"
    assert time.monotonic() - start < 0.1


class Response:
    def __init__(self, body=b"", headers=None, status=200):
        self.body = body
        self.status = status
        self.headers = email.message.Message()
        for key, value in (headers or {"Content-Type": "text/html"}).items():
            self.headers[key] = value
        self.reads = 0

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        self.reads += 1
        chunk, self.body = self.body[:size], self.body[size:]
        return chunk


class WatchSocket:
    def __init__(self):
        self.closed = False
        self.interrupted = threading.Event()

    def settimeout(self, value):
        pass

    def dup(self):
        return self

    def shutdown(self, how):
        self.interrupted.set()

    def close(self):
        self.closed = True


class Connection:
    def __init__(self, response):
        self.sock = WatchSocket()
        self.response = response
        self.closed = False

    def connect(self):
        pass

    def request(self, *args, **kwargs):
        pass

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


def mock_reader(monkeypatch, response):
    connection = Connection(response)
    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", lambda *args, **kwargs: address())
    monkeypatch.setattr(fetch_url, "_pinned_connection", lambda *args: connection)
    return connection


def test_chunked_or_unknown_length_body_has_an_enforced_cap(monkeypatch):
    monkeypatch.setattr(fetch_url, "MAX_BYTES", 32)
    response = Response(b"x" * 100)
    connection = mock_reader(monkeypatch, response)
    result = fetch_url.fetch_article("https://example.com/")
    assert not result["ok"] and response.reads == 1
    assert connection.closed and connection.sock.closed


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "text/html", "Content-Length": "999999999"},
        {"Content-Type": "text/html", "Content-Encoding": "gzip"},
        {"Content-Type": "application/octet-stream"},
    ],
)
def test_rejected_envelopes_are_never_read(monkeypatch, headers):
    response = Response(b"x" * 100, headers)
    connection = mock_reader(monkeypatch, response)
    assert not fetch_url.fetch_article("https://example.com/")["ok"]
    assert response.reads == 0 and connection.closed


def test_watchdog_interrupts_a_drip_fed_header(monkeypatch):
    monkeypatch.setattr(fetch_url, "TIMEOUT", 0.04)
    connection = mock_reader(monkeypatch, Response())

    def header():
        assert connection.sock.interrupted.wait(0.5)
        raise ConnectionError("closed by deadline")

    connection.getresponse = header
    assert fetch_url.fetch_article("https://example.com/")["error"] == "timeout"
    assert connection.closed and connection.sock.closed


def test_redirect_is_validated_before_its_request(monkeypatch):
    requested = []

    def resolve(host, *args, **kwargs):
        return address("127.0.0.1") if host == "private.example" else address()

    def connect(target, deadline):
        requested.append(target[1])
        return Connection(Response(headers={"Location": "https://private.example/"}, status=302))

    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(fetch_url, "_pinned_connection", connect)
    assert fetch_url.fetch_article("https://example.com/")["error"] == "unsafe_url"
    assert requested == ["example.com"]


def test_success_preserves_redirect_chain_and_extracts_bounded_text(monkeypatch):
    connections = []
    monkeypatch.setattr(fetch_url.socket, "getaddrinfo", lambda *a, **kw: address())

    def connect(target, deadline):
        if len(connections) == 0:
            response = Response(headers={"Location": "/article"}, status=302)
        else:
            response = Response(
                b"<html><title>Example</title><body>"
                + b"Garden flowers are lovely. " * 100
                + b"</body></html>"
            )
        connection = Connection(response)
        connections.append(connection)
        return connection

    monkeypatch.setattr(fetch_url, "_pinned_connection", connect)
    result = fetch_url.fetch_article("https://example.com/")
    assert result["ok"] and result["title"] == "Example"
    assert result["urls"] == ["https://example.com/", "https://example.com/article"]
    assert all(connection.closed for connection in connections)


def test_real_tls_fetch_pins_tcp_but_checks_sni_and_host_certificates(tmp_path, monkeypatch):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "article.test")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(UTC) + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("article.test")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_file, key_file = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_file.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    received_hosts, server_names = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received_hosts.append(self.headers["Host"])
            if self.path == "/slow-headers":
                for value in b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n":
                    try:
                        self.connection.sendall(bytes([value]))
                    except OSError:
                        break
                    time.sleep(0.02)
                return
            body = b"<html><body>" + b"A pleasant article about flowers. " * 4 + b"</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                if self.path == "/slow-body":
                    self.wfile.write(body[:1])
                    time.sleep(0.4)
                    self.wfile.write(body[1:])
                else:
                    self.wfile.write(body)
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_file, key_file)
    server_context.set_servername_callback(
        lambda sock, server_name, context: server_names.append(server_name)
    )
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    client_context = ssl.create_default_context(cafile=str(cert_file))
    monkeypatch.setattr(fetch_url.ssl, "create_default_context", lambda: client_context)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    port = server.server_port
    try:
        target = (
            urlparse(f"https://article.test:{port}/"),
            "article.test",
            port,
            socket.AF_INET,
            "127.0.0.1",
        )
        location, html = fetch_url._fetch_hop(target, time.monotonic() + 5)
        assert location is None and "flowers" in html
        assert received_hosts == [f"article.test:{port}"] and server_names == ["article.test"]
        wrong = (
            urlparse(f"https://wrong.test:{port}/"),
            "wrong.test",
            port,
            socket.AF_INET,
            "127.0.0.1",
        )
        with pytest.raises(ssl.SSLCertVerificationError):
            fetch_url._fetch_hop(wrong, time.monotonic() + 5)
        assert len(received_hosts) == 1
        for path in ("/slow-headers", "/slow-body"):
            slow = (urlparse(f"https://article.test:{port}{path}"), *target[1:])
            start = time.monotonic()
            with pytest.raises(TimeoutError):
                fetch_url._fetch_hop(slow, start + 0.08)
            assert time.monotonic() - start < 0.3
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)
