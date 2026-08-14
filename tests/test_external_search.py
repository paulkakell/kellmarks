from __future__ import annotations

import json

import app as kellmarks


class FakeResponse:
    def __init__(self, payload: dict, url: str = "https://api.duckduckgo.com/") -> None:
        self.payload = json.dumps(payload).encode("utf-8")
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, amount: int) -> bytes:
        return self.payload[:amount]


def test_external_search_filters_unsafe_result_urls(client, monkeypatch) -> None:
    monkeypatch.setattr(
        kellmarks.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(
            {
                "Results": [
                    {"FirstURL": "javascript:alert(1)", "Text": "Unsafe"},
                    {"FirstURL": "https://safe.example/result", "Text": "Safe - result"},
                ],
                "RelatedTopics": [],
            }
        ),
    )
    response = client.get("/api/external/ddg", query_string={"q": "safe"})
    assert response.status_code == 200
    assert response.get_json()["results"] == [
        {
            "url": "https://safe.example/result",
            "title": "Safe",
            "snippet": "Safe - result",
        }
    ]


def test_external_search_rejects_untrusted_redirect(client, monkeypatch) -> None:
    monkeypatch.setattr(
        kellmarks.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({}, "https://evil.example/redirect"),
    )
    response = client.get("/api/external/ddg", query_string={"q": "safe"})
    assert response.status_code == 502


def test_external_search_is_rate_limited(make_app, monkeypatch) -> None:
    app = make_app(DDG_RATE_LIMIT=1)
    client = app.test_client()
    monkeypatch.setattr(
        kellmarks.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse({"Results": [], "RelatedTopics": []}),
    )
    assert client.get("/api/external/ddg", query_string={"q": "one"}).status_code == 200
    assert client.get("/api/external/ddg", query_string={"q": "two"}).status_code == 429


def test_external_query_length_is_limited(client) -> None:
    response = client.get("/api/external/ddg", query_string={"q": "x" * 257})
    assert response.status_code == 400
