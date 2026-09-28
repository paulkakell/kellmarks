"""Regression for the explicit metadata TLS floor and certificate validation."""
from __future__ import annotations

import socket
import ssl

import metadata


def test_metadata_sets_tls_floor_before_handshake_and_retains_verification(monkeypatch):
    context = ssl.create_default_context()
    # An explicitly permissive context simulates an older/default-policy drift.
    # No real handshake or network request is made in this regression.
    context.minimum_version = ssl.TLSVersion.MINIMUM_SUPPORTED
    observed = []

    class Socket:
        def settimeout(self, value):
            pass

        def connect(self, target):
            assert target == ("93.184.216.34", 443)

        def getpeername(self):
            return ("93.184.216.34", 443)

        def close(self):
            pass

        def shutdown(self, how):
            pass

    def wrap(self, sock, *, server_hostname):
        observed.append((self.minimum_version, self.verify_mode,
                         self.check_hostname, server_hostname))
        raise OSError("stop before a real handshake")

    monkeypatch.setattr(metadata.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ])
    monkeypatch.setattr(metadata.socket, "socket", lambda *args: Socket())
    monkeypatch.setattr(metadata.ssl, "create_default_context", lambda: context)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    assert metadata.DescriptionFetcher().fetch("https://example.com").status == "unavailable"
    assert observed == [(ssl.TLSVersion.TLSv1_2, ssl.CERT_REQUIRED, True, "example.com")]
