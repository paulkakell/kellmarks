"""Single-instance production configuration for the file-backed application."""
from __future__ import annotations

import os


def require_authentication() -> None:
    token = os.environ.get("KELLMARKS_AUTH_TOKEN", "")
    if (
        len(token) < 32
        or not token.isascii()
        or any(ord(character) <= 32 or ord(character) == 127 for character in token)
    ):
        raise RuntimeError(
            "Docker requires KELLMARKS_AUTH_TOKEN: at least 32 printable ASCII "
            "characters without whitespace. See docs/INSTALLATION.md."
        )
    os.environ["KELLMARKS_REQUIRE_AUTH"] = "1"


require_authentication()

bind = "0.0.0.0:8787"
# Rate limits and release caches are process-local. Do not multiply them by scaling.
workers = 1
worker_class = "gthread"
threads = 4
timeout = 60
graceful_timeout = 30
keepalive = 5
# Container-private tmpfs; Gunicorn securely creates worker temporary files.
worker_tmp_dir = "/tmp"  # nosec B108
umask = 0o077
# The app validates the public origin and never trusts proxy identity headers.
forwarded_allow_ips = ""
secure_scheme_headers = {}
# Flask already emits structured API logs without credentials or query strings.
accesslog = None
errorlog = "-"
loglevel = "info"
capture_output = True
