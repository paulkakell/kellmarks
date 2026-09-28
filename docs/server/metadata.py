"""Opt-in, bounded HTML-description retrieval from public HTTP(S) sites only.

Every DNS answer and redirect is checked. Connections use a validated numeric
address, while HTTPS still verifies the original hostname. No proxy, cookies,
authorization, referrer, browser execution, or third-party scraping service.
"""
from __future__ import annotations

import codecs
import http.client
import ipaddress
import re
import socket
import ssl
import threading
import time
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass
from html.parser import HTMLParser

MAX_HTML_BYTES = 262_144
MAX_DESCRIPTION_LENGTH = 600
MAX_REDIRECTS = 3
FETCH_TIMEOUT = 6.0
MAX_WORKERS = 4
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE)
ENCODED_CONTROL = re.compile(r"%(?:0[0-9a-f]|1[0-9a-f]|7f)", re.IGNORECASE)


class UnsafeTarget(ValueError):
    """The supplied target is outside the public-web fetch policy."""


@dataclass(frozen=True)
class DescriptionResult:
    description: str = ""
    status: str = "unavailable"


def clean_description(value: str) -> str:
    value = ENCODED_CONTROL.sub(" ", value)
    value = re.sub(r"[\x00-\x1f\x7f]", " ", value)
    return " ".join(value.split())[:MAX_DESCRIPTION_LENGTH]


class DescriptionParser(HTMLParser):
    """Read metadata only; never load resources or execute embedded markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        if tag == "body":
            self.done = True
        if tag != "meta":
            return
        attributes = dict(attrs)
        key = (attributes.get("name") or attributes.get("property") or "").strip().lower()
        if key in {"description", "og:description", "twitter:description"}:
            value = clean_description(attributes.get("content") or "")
            if value and key not in self.values:
                self.values[key] = value

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.done = True

    def result(self) -> DescriptionResult:
        for key in ("description", "og:description", "twitter:description"):
            if key in self.values:
                return DescriptionResult(self.values[key], "fetched")
        return DescriptionResult(status="missing")


def target_parts(url: str) -> tuple[str, str, int, str]:
    if not isinstance(url, str) or not url or len(url) > 2048:
        raise UnsafeTarget("invalid URL length")
    if (re.search(r"[\x00-\x20\x7f\\]", url) or ENCODED_CONTROL.search(url)
            or re.search(r"%(?![0-9a-fA-F]{2})", url)):
        raise UnsafeTarget("invalid URL characters")
    try:
        parsed = urllib.parse.urlsplit(url)
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").rstrip(".").encode("idna").decode("ascii").lower()
        port = parsed.port if parsed.port is not None else (443 if scheme == "https" else 80)
        if (scheme not in {"http", "https"} or not hostname or len(hostname) > 253
                or "%" in hostname or parsed.username is not None or parsed.password is not None
                or port != (443 if scheme == "https" else 80)):
            raise UnsafeTarget("only credential-free public HTTP(S) on default ports is allowed")
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            if ("." not in hostname or any(not HOST_LABEL.fullmatch(label)
                    for label in hostname.split("."))):
                raise UnsafeTarget("invalid public hostname") from None
        # Fragments never go on the wire. Encode Unicode paths without changing
        # already escaped path/query bytes or interpreting an authority in a path.
        path = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        path = urllib.parse.quote(path, safe="/%:@!$&'()*+,;=-._~?")
        return scheme, hostname, port, path
    except (ValueError, UnicodeError) as exc:
        raise UnsafeTarget("invalid public URL") from exc


def public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not address.is_global or address.is_multicast or address.is_reserved:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        # Exclude mapped/transition addresses and translation prefixes, including
        # NAT64, rather than trusting an embedded or translated private IPv4.
        return (address in ipaddress.IPv6Network("2000::/3")
                and address.sixtofour is None and address.teredo is None)
    return True


class RequestBudget:
    def __init__(self, timeout: float) -> None:
        self.deadline = time.monotonic() + timeout
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.sock: socket.socket | None = None

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self.cancelled.is_set() or remaining <= 0:
            raise TimeoutError("metadata deadline exceeded")
        return min(remaining, 3.0)

    def attach(self, sock: socket.socket) -> None:
        with self.lock:
            if self.cancelled.is_set():
                sock.close()
                raise TimeoutError("metadata request cancelled")
            self.sock = sock

    def cancel(self) -> None:
        self.cancelled.set()
        with self.lock:
            sock, self.sock = self.sock, None
        if sock is not None:
            with suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)
            sock.close()


def request_description(
    url: str, budget: RequestBudget,
) -> tuple[DescriptionResult, str | None]:
    scheme, hostname, port, path = target_parts(url)
    budget.remaining()
    answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    budget.remaining()  # A late DNS result must never start an outbound connection.
    if (not answers or any(answer[0] not in {socket.AF_INET, socket.AF_INET6}
            or not public_address(str(answer[4][0])) for answer in answers)):
        raise UnsafeTarget("DNS returned a non-public address")
    family, socktype, protocol, _, sockaddr = answers[0]
    # Connect to exactly the address that was checked, not the hostname again.
    connection = http.client.HTTPConnection(hostname, port, timeout=budget.remaining())
    sock = socket.socket(family, socktype, protocol)
    try:
        budget.attach(sock)
        sock.settimeout(budget.remaining())
        sock.connect(sockaddr)
        if (not public_address(sock.getpeername()[0])
                or ipaddress.ip_address(sock.getpeername()[0]) != ipaddress.ip_address(sockaddr[0])):
            raise UnsafeTarget("non-public peer")
        if scheme == "https":
            sock.settimeout(budget.remaining())
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=hostname)
            budget.attach(sock)
        connection.sock = sock
        sock.settimeout(budget.remaining())
        connection.request("GET", path, headers={
            "User-Agent": "Kellmarks-Description/1.0",
            "Accept": "text/html, application/xhtml+xml",
            "Accept-Encoding": "identity",
            "Connection": "close",
        })
        sock.settimeout(budget.remaining())
        response = connection.getresponse()
        try:
            if response.status in REDIRECT_STATUSES:
                location = response.getheader("Location")
                if not location:
                    return DescriptionResult(), None
                redirected = urllib.parse.urljoin(url, location)
                new_scheme, _, _, _ = target_parts(redirected)
                if scheme == "https" and new_scheme != "https":
                    raise UnsafeTarget("HTTPS downgrade refused")
                return DescriptionResult(), redirected
            if not 200 <= response.status < 300:
                return DescriptionResult(), None
            if response.headers.get_content_type() not in {"text/html", "application/xhtml+xml"}:
                return DescriptionResult(status="unsupported"), None
            if response.getheader("Content-Encoding", "identity").lower() != "identity":
                return DescriptionResult(status="unsupported"), None
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                decoder = codecs.getincrementaldecoder(charset)(errors="replace")
            except LookupError:
                decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            parser = DescriptionParser()
            size = 0
            while size < MAX_HTML_BYTES and not parser.done:
                sock.settimeout(budget.remaining())
                chunk = response.read1(min(16_384, MAX_HTML_BYTES - size))
                if not chunk:
                    break
                size += len(chunk)
                parser.feed(decoder.decode(chunk))
            parser.feed(decoder.decode(b"", final=True))
            parser.close()
            return parser.result(), None
        finally:
            response.close()
    finally:
        connection.close()
        sock.close()


def retrieve_description(url: str, budget: RequestBudget) -> DescriptionResult:
    for attempt in range(MAX_REDIRECTS + 1):
        result, redirect = request_description(url, budget)
        if redirect is None:
            return result
        if attempt == MAX_REDIRECTS:
            return DescriptionResult(status="redirect-limit")
        url = redirect
    return DescriptionResult()  # Defensive fallback; the bounded loop always returns.


class DescriptionFetcher:
    """Bound concurrency and wall time, including otherwise unbounded OS DNS.

    At most four daemon workers can exist per service. A resolver stuck in the
    OS keeps one slot until it returns; new work fails closed instead of queuing.
    Timed-out workers close their sockets and may not connect after late DNS.
    """

    def __init__(self, *, timeout: float = FETCH_TIMEOUT, workers: int = MAX_WORKERS) -> None:
        self.timeout = timeout
        self.slots = threading.BoundedSemaphore(workers)

    def fetch(self, url: str) -> DescriptionResult:
        if not self.slots.acquire(blocking=False):
            return DescriptionResult(status="busy")
        budget = RequestBudget(self.timeout)
        done = threading.Event()
        result = [DescriptionResult()]

        def work() -> None:
            try:
                result[0] = retrieve_description(url, budget)
            except UnsafeTarget:
                result[0] = DescriptionResult(status="blocked")
            except (OSError, http.client.HTTPException, ValueError, UnicodeError):
                result[0] = DescriptionResult(status="unavailable")
            finally:
                budget.cancel()
                self.slots.release()
                done.set()

        worker = threading.Thread(target=work, name="kellmarks-description", daemon=True)
        try:
            worker.start()
        except RuntimeError:
            self.slots.release()
            return DescriptionResult(status="busy")
        if not done.wait(max(0, budget.deadline - time.monotonic())):
            budget.cancel()
            return DescriptionResult(status="unavailable")
        return result[0]
