"""Bounded, cached release checks against one fixed public GitHub endpoint."""
from __future__ import annotations

import http.client
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

RELEASE_API = "https://api.github.com/repos/paulkakell/kellmarks/releases/latest"
RELEASE_PAGE = "https://github.com/paulkakell/kellmarks/releases/latest"
MAX_RELEASE_BYTES = 262_144
SUCCESS_TTL = 3_600
FAILURE_TTL = 300
VERSION_RE = re.compile(r"v?([0-9]{1,6})\.([0-9]{1,6})\.([0-9]{1,6})", re.IGNORECASE)


def version_parts(value: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(value)
    if not match:
        raise ValueError("unsupported release version")
    return int(match[1]), int(match[2]), int(match[3])


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int,
        msg: str, headers: Any, newurl: str,
    ) -> None:
        # Returning None rejects redirects before making any request to their targets.
        return None


class ReleaseChecker:
    def __init__(self, current_version: str) -> None:
        self.current_version = current_version
        self.current_parts = version_parts(current_version)
        self._opener = urllib.request.build_opener(NoRedirects())
        self._lock = threading.Lock()
        self._cached: dict[str, Any] | None = None
        self._expires = 0.0

    def _result(self, status: str) -> dict[str, Any]:
        return {
            "currentVersion": self.current_version,
            "latestVersion": None,
            "status": status,
            "releaseUrl": RELEASE_PAGE,
            "checkedAt": None,
        }

    def check(self, *, allowed: bool) -> dict[str, Any]:
        if not allowed:
            return self._result("disabled")
        with self._lock:
            if self._cached is not None and time.monotonic() < self._expires:
                return dict(self._cached)
            result = self._result("unavailable")
            ttl = FAILURE_TTL
            outbound = urllib.request.Request(
                RELEASE_API,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"Kellmarks/{self.current_version}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                method="GET",
            )
            try:
                with self._opener.open(outbound, timeout=4) as upstream:  # nosec B310
                    if upstream.geturl() != RELEASE_API:
                        raise ValueError("unexpected release endpoint")
                    raw = upstream.read(MAX_RELEASE_BYTES + 1)
                if len(raw) > MAX_RELEASE_BYTES:
                    raise ValueError("release response exceeds limit")
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict) or data.get("draft") is not False or data.get("prerelease") is not False:
                    raise ValueError("expected a published stable release")
                tag = data.get("tag_name")
                if not isinstance(tag, str):
                    raise ValueError("release tag is missing")
                latest = version_parts(tag)
                result["latestVersion"] = tag.lstrip("vV")
                result["releaseUrl"] = (
                    "https://github.com/paulkakell/kellmarks/releases/tag/"
                    + urllib.parse.quote(tag, safe="")
                )
                result["status"] = (
                    "update_available" if latest > self.current_parts
                    else "ahead" if latest < self.current_parts else "current"
                )
                ttl = SUCCESS_TTL
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    result["status"] = "no_release"
                exc.close()
            except (OSError, ValueError, http.client.HTTPException, RecursionError):
                # Offline, rate-limited and malformed responses never mean "up to date".
                pass
            result["checkedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            self._cached = result
            self._expires = time.monotonic() + ttl
            return dict(result)
