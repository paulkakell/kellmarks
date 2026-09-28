from __future__ import annotations

import io
import socket
import threading
import time
from typing import Any

import metadata
import pytest
from metadata import DescriptionFetcher, DescriptionParser, DescriptionResult, RequestBudget


class Stream(io.BytesIO):
    def __init__(self, content: bytes) -> None:
        super().__init__(content)
        self.body_bytes = 0

    def read1(self, size: int = -1) -> bytes:
        data = super().read1(size)
        self.body_bytes += len(data)
        return data


class FakeSocket:
    def __init__(self, packet: bytes) -> None:
        self.stream = Stream(packet)
        self.sent = b""
        self.peer = ("93.184.216.34", 443)
        self.closed = False
        self.connected: Any = None

    def connect(self, address: Any) -> None:
        self.connected = address
        self.peer = address

    def getpeername(self) -> Any:
        return self.peer

    def settimeout(self, timeout: float) -> None:
        assert 0 < timeout <= 3

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def makefile(self, mode: str) -> Stream:
        assert mode == "rb"
        return self.stream

    def shutdown(self, how: int) -> None:
        self.closed = True

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def network(monkeypatch):
    packets: list[bytes] = []
    connections: list[FakeSocket] = []
    resolutions: list[str] = []
    tls_hosts: list[str] = []

    def resolve(host, port, **kwargs):
        resolutions.append(host)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    def create_socket(*args):
        sock = FakeSocket(packets.pop(0))
        connections.append(sock)
        return sock

    class TLS:
        def wrap_socket(self, sock, *, server_hostname):
            tls_hosts.append(server_hostname)
            return sock

    monkeypatch.setattr(metadata.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(metadata.socket, "socket", create_socket)
    monkeypatch.setattr(metadata.ssl, "create_default_context", TLS)

    def response(body=b"", *, status=200, headers=None):
        if isinstance(body, str):
            body = body.encode()
        fields = {"Content-Type": "text/html; charset=utf-8", "Content-Length": str(len(body))}
        fields.update(headers or {})
        packet = f"HTTP/1.1 {status} Test\r\n".encode()
        packet += b"".join(f"{name}: {value}\r\n".encode() for name, value in fields.items())
        packets.append(packet + b"\r\n" + body)

    return response, connections, resolutions, tls_hosts


def test_metadata_precedence_case_entities_and_plain_text():
    parser = DescriptionParser()
    parser.feed('''<html><head>
      <meta property="og:description" content="Open Graph">
      <meta name="twitter:description" content="Twitter">
      <META NAME="Description" CONTENT="  Main &amp; safe&#10;text &lt;b&gt;literal&lt;/b&gt; ">
      <meta name="description" content="Must not replace the first">
      </head><body><meta name="description" content="Body ignored"></body>''')
    assert parser.result() == DescriptionResult("Main & safe text <b>literal</b>", "fetched")


@pytest.mark.parametrize(("html", "expected"), [
    ('<meta name="description" content=" "><meta property="og:description" content="OG">', "OG"),
    ('<meta property="twitter:description" content="Tweet" />', "Tweet"),
    ('<meta name="description"><meta name="twitter:description" content="Fallback">', "Fallback"),
    ('<body><meta name="description" content="ignored">', ""),
    ('<script>"<meta name=description content=ignored>"</script>', ""),
    ('<title>Not a description</title>', ""),
    ('<meta name="description" content="a%0Ab&#0;c\td">', "a b�c d"),
])
def test_parser_fallbacks(html, expected):
    parser = DescriptionParser()
    parser.feed(html)
    assert parser.result().description == expected


def test_description_is_bounded_and_removes_control_characters():
    assert metadata.clean_description(" one\x00 two%7fthree\n ") == "one two three"
    assert len(metadata.clean_description("x" * 1000)) == 600


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "http://user:password@example.com",
    "https://example.com:8443", "http://example.com:443", "https://example.com:0",
    "https://example.com:99999", "https://example.com:bad", "http://localhost/x",
    "http://example.com\\@127.0.0.1", "https://example.com/%0d%0aHost:x",
    "http://example.com/\x00", "http://example.com/%xx", "http://bad_host.example/x",
    "http://-bad.example", "http://example..com", "http://[fe80::1%25eth0]/",
    "//example.com/x", "https://", "", "http://example.com/" + "a" * 2048,
])
def test_reject_unsafe_url_shapes_before_dns(monkeypatch, url):
    monkeypatch.setattr(metadata.socket, "getaddrinfo", lambda *args, **kwargs: pytest.fail("DNS"))
    assert DescriptionFetcher().fetch(url).status == "blocked"


@pytest.mark.parametrize("address", [
    "127.0.0.1", "0.0.0.0", "10.0.0.1", "172.16.0.1", "192.168.1.1",
    "169.254.169.254", "100.64.0.1", "192.0.0.1", "192.0.2.1", "198.18.0.1",
    "224.0.0.1", "255.255.255.255", "::1", "::", "fc00::1", "fe80::1",
    "ff02::1", "::ffff:127.0.0.1", "64:ff9b::7f00:1", "64:ff9b::808:808",
    "2002:7f00:1::", "2001::1", "2001:db8::1", "not-an-address",
])
def test_non_public_and_transition_addresses_are_blocked(address):
    assert not metadata.public_address(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "8.8.8.8", "2606:4700:4700::1111"])
def test_global_unicast_addresses_are_supported(address):
    assert metadata.public_address(address)


def test_connect_pins_dns_and_retains_tls_hostname_without_credentials(network):
    response, connections, resolutions, tls_hosts = network
    response('<head><meta name="description" content="Site summary"></head>')
    result = DescriptionFetcher().fetch("https://example.com/path?q=one#never-sent")
    assert result == DescriptionResult("Site summary", "fetched")
    assert resolutions == ["example.com"]  # No second DNS lookup during connect.
    assert connections[0].connected == ("93.184.216.34", 443)
    assert tls_hosts == ["example.com"]
    sent = connections[0].sent.decode()
    assert "GET /path?q=one HTTP/1.1" in sent
    assert "Host: example.com:443" in sent
    assert "Accept-Encoding: identity" in sent
    assert all(value not in sent.lower() for value in ["authorization", "cookie", "referer", "never-sent"])
    assert connections[0].closed


def test_http_uses_default_port_and_encodes_unicode_path(network):
    response, connections, _, tls_hosts = network
    response('<meta name="description" content="HTTP">')
    assert DescriptionFetcher().fetch("http://example.com/café").description == "HTTP"
    assert connections[0].connected[1] == 80
    assert b"GET /caf%C3%A9 " in connections[0].sent
    assert tls_hosts == []


def test_mixed_dns_answers_are_all_validated(network, monkeypatch):
    _, connections, _, _ = network
    monkeypatch.setattr(metadata.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    assert DescriptionFetcher().fetch("https://example.com").status == "blocked"
    assert connections == []


@pytest.mark.parametrize("answers", [[], [(socket.AF_UNIX, socket.SOCK_STREAM, 0, "", "x")]])
def test_empty_or_unsupported_dns_answers_fail_closed(network, monkeypatch, answers):
    monkeypatch.setattr(metadata.socket, "getaddrinfo", lambda *args, **kwargs: answers)
    assert DescriptionFetcher().fetch("https://example.com").status == "blocked"
    assert not network[1]


def test_redirect_revalidates_private_target(network, monkeypatch):
    response, connections, _, _ = network
    response(status=302, headers={"Location": "https://internal.example/secret"})
    def resolve(host, port, **kwargs):
        ip = "127.0.0.1" if host == "internal.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(metadata.socket, "getaddrinfo", resolve)
    assert DescriptionFetcher().fetch("https://example.com").status == "blocked"
    assert len(connections) == 1


def test_relative_redirect_and_rebinding(network, monkeypatch):
    response, connections, _, _ = network
    response(status=301, headers={"Location": "/next"})
    response('<meta property="og:description" content="Redirected">')
    assert DescriptionFetcher().fetch("https://example.com/start").description == "Redirected"
    assert len(connections) == 2
    assert b"GET /next " in connections[1].sent
    response(status=301, headers={"Location": "/next"})
    calls = []
    def resolve(host, port, **kwargs):
        calls.append(host)
        ip = "93.184.216.34" if len(calls) == 1 else "169.254.169.254"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]
    monkeypatch.setattr(metadata.socket, "getaddrinfo", resolve)
    assert DescriptionFetcher().fetch("https://example.com/start").status == "blocked"
    assert len(connections) == 3


@pytest.mark.parametrize("target", ["http://example.com", "file:///etc/passwd", "https://u:p@example.com"])
def test_redirect_rejects_downgrade_schemes_and_credentials(network, target):
    network[0](status=302, headers={"Location": target})
    assert DescriptionFetcher().fetch("https://example.com").status == "blocked"
    assert len(network[1]) == 1


def test_redirect_chain_is_bounded(network):
    for _ in range(4):
        network[0](status=302, headers={"Location": "/again"})
    assert DescriptionFetcher().fetch("https://example.com").status == "redirect-limit"
    assert len(network[1]) == 4


@pytest.mark.parametrize(("status", "headers", "expected"), [
    (302, {}, "unavailable"), (404, {}, "unavailable"), (503, {}, "unavailable"),
    (200, {"Content-Type": "application/json"}, "unsupported"),
    (200, {"Content-Encoding": "gzip"}, "unsupported"),
    (200, {}, "missing"),
])
def test_http_failures_and_non_html(network, status, headers, expected):
    network[0](status=status, headers=headers)
    assert DescriptionFetcher().fetch("https://example.com").status == expected
    assert network[1][0].closed


def test_declared_charset_and_unknown_charset_fallback(network):
    network[0]('<meta name="description" content="café">'.encode("latin-1"),
               headers={"Content-Type": "text/html; charset=iso-8859-1"})
    assert DescriptionFetcher().fetch("https://example.com").description == "café"
    network[0]('<meta name="description" content="café">',
               headers={"Content-Type": "text/html; charset=nonexistent-charset"})
    assert DescriptionFetcher().fetch("https://example.com").description == "café"


def test_html_read_limit_and_early_head_stop(network):
    body = '<meta name="description" content="First">' + ' ' * (metadata.MAX_HTML_BYTES * 2)
    network[0](body)
    assert DescriptionFetcher().fetch("https://example.com").description == "First"
    assert network[1][-1].stream.body_bytes == metadata.MAX_HTML_BYTES
    network[0]('<head><meta name="description" content="Head"></head>' + 'x' * 1_000_000)
    assert DescriptionFetcher().fetch("https://example.com").description == "Head"
    assert network[1][-1].stream.body_bytes <= 16_384


def test_peer_must_match_validated_address(network, monkeypatch):
    network[0]('<meta name="description" content="No">')
    monkeypatch.setattr(FakeSocket, "getpeername", lambda self: ("8.8.8.8", 443))
    assert DescriptionFetcher().fetch("https://example.com").status == "blocked"
    assert network[1][0].sent == b""


def test_invalid_tls_certificate_never_sends_http(network, monkeypatch):
    network[0]('<meta name="description" content="No">')
    class BrokenTLS:
        def wrap_socket(self, *args, **kwargs):
            raise metadata.ssl.SSLCertVerificationError("untrusted")
    monkeypatch.setattr(metadata.ssl, "create_default_context", BrokenTLS)
    assert DescriptionFetcher().fetch("https://example.com").status == "unavailable"
    assert network[1][0].sent == b""


def test_dns_error_and_malformed_http_are_nonfatal(network, monkeypatch):
    def failure(*args, **kwargs):
        raise socket.gaierror("unreachable")
    with monkeypatch.context() as patch:
        patch.setattr(metadata.socket, "getaddrinfo", failure)
        assert DescriptionFetcher().fetch("https://example.com").status == "unavailable"
    network[0]('<meta name="description" content="Never">')
    monkeypatch.setattr(FakeSocket, "makefile", lambda *args: io.BytesIO(b"not HTTP\r\n"))
    assert DescriptionFetcher().fetch("https://example.com").status == "unavailable"


def test_deadline_covers_dns_and_busy_workers_do_not_queue(network, monkeypatch):
    release = threading.Event()
    entered = threading.Event()
    def stalled(*args, **kwargs):
        entered.set()
        release.wait(timeout=2)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
    monkeypatch.setattr(metadata.socket, "getaddrinfo", stalled)
    fetcher = DescriptionFetcher(timeout=0.04, workers=1)
    start = time.monotonic()
    try:
        assert fetcher.fetch("https://example.com").status == "unavailable"
        assert entered.is_set()
        assert time.monotonic() - start < 1
        assert fetcher.fetch("https://other.example").status == "busy"
    finally:
        release.set()
    assert fetcher.slots.acquire(timeout=1)
    fetcher.slots.release()
    assert network[1] == []  # Late resolution cannot start a connection.


def test_budget_cancel_closes_socket_and_rejects_late_attach():
    budget = RequestBudget(1)
    sock = FakeSocket(b"")
    budget.attach(sock)
    budget.cancel()
    assert sock.closed
    with pytest.raises(TimeoutError):
        budget.remaining()
    other = FakeSocket(b"")
    with pytest.raises(TimeoutError):
        budget.attach(other)
    assert other.closed


def test_thread_start_failure_releases_slot(monkeypatch):
    def failure(self):
        raise RuntimeError("thread unavailable")
    monkeypatch.setattr(threading.Thread, "start", failure)
    fetcher = DescriptionFetcher(workers=1)
    assert fetcher.fetch("https://example.com").status == "busy"
    assert fetcher.slots.acquire(blocking=False)


@pytest.fixture
def lookup(app, monkeypatch):
    urls = []
    def fetch(url):
        urls.append(url)
        return DescriptionResult("Fetched site description", "fetched")
    monkeypatch.setattr(app.extensions["kellmarks_description_fetcher"], "fetch", fetch)
    return urls


def test_create_opt_in_fills_blank_without_changing_schema_or_tags(client, lookup):
    result = client.post("/api/entries", json={"title": "Page", "url": "https://example.com",
                                            "description": "  ", "fetchDescription": True})
    assert result.status_code == 201
    entry = result.get_json()
    assert entry["description"] == "Fetched site description"
    assert result.headers["X-Kellmarks-Description-Status"] == "fetched"
    assert lookup == ["https://example.com"]
    assert "fetchDescription" not in entry
    assert client.get('/api/entries/' + entry['id']).get_json() == entry
    exported = client.get("/api/export").get_json()
    assert exported["version"] == 2
    assert exported["entries"][0]["description"] == "Fetched site description"


def test_default_and_existing_descriptions_never_fetch(client, lookup):
    for extra in [{}, {"fetchDescription": False}, {"description": "Mine", "fetchDescription": True}]:
        result = client.post("/api/entries", json={"title": "Page", "url": "https://example.com", **extra})
        assert result.status_code == 201
        assert result.get_json()["description"] == extra.get("description", "")
    assert lookup == []


def test_operator_denial_overrides_explicit_consent(app, client, lookup):
    app.config["EXTERNAL_REQUESTS_ALLOWED"] = False
    result = client.post("/api/entries", json={"url": "https://example.com", "fetchDescription": True})
    assert result.status_code == 201
    assert result.headers["X-Kellmarks-Description-Status"] == "disabled"
    assert not result.get_json()["description"]
    assert lookup == []


@pytest.mark.parametrize("value", [None, "true", 1, [], {}])
def test_fetch_consent_must_be_boolean(client, lookup, value):
    result = client.post("/api/entries", json={"url": "https://example.com", "fetchDescription": value})
    assert result.status_code == 400
    assert lookup == []
    assert client.get("/api/entries").get_json() == []


def test_edits_imports_search_and_render_data_do_not_fetch(client, lookup):
    entry = client.post("/api/entries", json={"url": "https://example.com"}).get_json()
    result = client.put("/api/entries/" + entry["id"], json={"description": "", "fetchDescription": True})
    assert result.status_code == 200 and result.get_json()["description"] == ""
    result = client.post("/api/import", json={"entries": [{"url": "https://example.com", "fetchDescription": True}]})
    assert result.status_code == 200
    assert client.get("/api/search?q=example").status_code == 200
    with client.get("/") as response:
        assert response.status_code == 200
        response.get_data()
    assert lookup == []


def test_auth_and_invalid_fields_fail_before_network(app, client, lookup):
    assert client.post("/api/entries", json={"url": "ftp://example.com", "fetchDescription": True}).status_code == 400
    app.config["AUTH_TOKEN"] = "a" * 40
    assert client.post("/api/entries", json={"url": "https://example.com", "fetchDescription": True}).status_code == 401
    assert lookup == []


def test_metadata_rate_limit_keeps_bookmark_creation_working(app, client, lookup):
    app.config["METADATA_RATE_LIMIT"] = 1
    payload = {"url": "https://example.com", "fetchDescription": True}
    assert client.post("/api/entries", json=payload).status_code == 201
    result = client.post("/api/entries", json=payload)
    assert result.status_code == 201
    assert result.headers["X-Kellmarks-Description-Status"] == "rate-limited"
    assert result.get_json()["description"] == ""
    assert len(lookup) == 1


@pytest.mark.parametrize("status", ["blocked", "missing", "unavailable", "unsupported", "busy", "redirect-limit"])
def test_lookup_failures_still_save(client, app, monkeypatch, status):
    monkeypatch.setattr(app.extensions["kellmarks_description_fetcher"], "fetch",
                        lambda url: DescriptionResult(status=status))
    result = client.post("/api/entries", json={"url": "https://example.com", "fetchDescription": True})
    assert result.status_code == 201
    assert result.get_json()["description"] == ""
    assert result.headers["X-Kellmarks-Description-Status"] == status


def test_full_library_does_not_contact_site(app, client, lookup):
    app.config["MAX_ENTRIES"] = 1
    client.post("/api/entries", json={"url": "https://example.com"})
    result = client.post("/api/entries", json={"url": "https://example.com", "fetchDescription": True})
    assert result.status_code == 400
    assert lookup == []


def test_concurrent_save_is_not_overwritten_after_metadata(app, client, monkeypatch):
    def fetch(url):
        with app.test_client() as other:
            result = other.post("/api/entries", json={"title": "Concurrent", "url": "https://other.example"})
            assert result.status_code == 201
        return DescriptionResult("Metadata", "fetched")
    monkeypatch.setattr(app.extensions["kellmarks_description_fetcher"], "fetch", fetch)
    assert client.post("/api/entries", json={"title": "Original", "url": "https://example.com", "fetchDescription": True}).status_code == 201
    assert {entry["title"] for entry in client.get("/api/entries").get_json()} == {"Original", "Concurrent"}
