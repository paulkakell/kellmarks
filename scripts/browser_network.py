"""Mock Chromium traffic, including image requests named /favicon.ico.

Playwright 1.57 classifies every URL ending in /favicon.ico as a browser
favicon, omits its request events and aborts it before page.route handlers.
Use Chromium's Fetch domain directly for icon scenarios so the real image
URL and actual decoding are tested, without changing application behavior.
Do not combine this interceptor with page.route on the same page.
"""
from __future__ import annotations

import base64
import json as json_module
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any


class BrowserRoute:
    def __init__(self, session: Any, event: dict[str, Any]) -> None:
        self._session = session
        self._request_id = event["requestId"]
        self.request = SimpleNamespace(url=event["request"]["url"])

    def continue_(self) -> None:
        self._session.send("Fetch.continueRequest", {"requestId": self._request_id})

    def abort(self) -> None:
        self._session.send("Fetch.failRequest", {
            "requestId": self._request_id, "errorReason": "Aborted",
        })

    def fulfill(
        self, *, json: Any = None, body: bytes = b"", status: int = 200,
        content_type: str = "application/octet-stream",
    ) -> None:
        if json is not None:
            body = json_module.dumps(json).encode("utf-8")
            content_type = "application/json"
        self._session.send("Fetch.fulfillRequest", {
            "requestId": self._request_id,
            "responseCode": status,
            "responseHeaders": [{"name": "Content-Type", "value": content_type}],
            "body": base64.b64encode(body).decode("ascii"),
        })


def intercept_requests(page: Any, handler: Callable[[BrowserRoute], None]) -> None:
    session = page.context.new_cdp_session(page)
    session.on("Fetch.requestPaused", lambda event: handler(BrowserRoute(session, event)))
    session.send("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})
