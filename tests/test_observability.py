from __future__ import annotations

import io
import json
import logging
import time

import app as kellmarks


def test_api_log_is_structured_and_omits_query_values(app) -> None:
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(logging.Formatter("%(message)s"))
    app.logger.addHandler(handler)
    try:
        response = app.test_client().get(
            "/api/search",
            query_string={"q": "private search terms", "path": "__ALL__"},
        )
    finally:
        app.logger.removeHandler(handler)
    assert response.status_code == 200
    records = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
    request_record = next(record for record in records if record["event"] == "api_request")
    assert request_record["path"] == "/api/search"
    assert request_record["status"] == 200
    assert request_record["durationMs"] >= 0
    assert "private search terms" not in output.getvalue()


def test_supplied_request_id_is_validated(client) -> None:
    valid = client.get("/api/health", headers={"X-Request-ID": "request-123"})
    assert valid.headers["X-Request-ID"] == "request-123"
    invalid = client.get("/api/health", headers={"X-Request-ID": "bad id with spaces"})
    assert invalid.headers["X-Request-ID"] != "bad id with spaces"
    assert len(invalid.headers["X-Request-ID"]) == 16


def test_search_performance_budget() -> None:
    entries = [
        {
            "id": f"entry-{index}",
            "title": f"Cloud security reference {index}",
            "url": f"https://example.com/{index}",
            "description": "identity vpn zero trust",
            "tags": ["work/security", "cloud/aws"],
        }
        for index in range(10_000)
    ]
    started = time.perf_counter()
    matches = [
        entry
        for entry in entries
        if kellmarks.matches_query(entry, 'vpn AND (aws OR azure) NOT personal')
    ]
    duration = time.perf_counter() - started
    assert len(matches) == 10_000
    assert duration < 3.0
