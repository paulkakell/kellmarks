"""Authenticated local liveness check; never print credentials or response bodies."""
from __future__ import annotations

import http.client
import json
import os
import sys


def main() -> int:
    token = os.environ.get("KELLMARKS_AUTH_TOKEN", "")
    host = os.environ.get("KELLMARKS_TRUSTED_HOSTS", "127.0.0.1").split(",")[0].strip()
    if not token or not host:
        return 1
    connection = http.client.HTTPConnection("127.0.0.1", 8787, timeout=3)
    try:
        connection.request(
            "GET", "/api/health",
            headers={"Authorization": f"Bearer {token}", "Host": host},
        )
        response = connection.getresponse()
        body = response.read(8193)
        if response.status != 200 or len(body) > 8192:
            return 1
        payload = json.loads(body)
        return 0 if isinstance(payload, dict) and payload.get("ok") is True else 1
    except (OSError, ValueError, http.client.HTTPException):
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
