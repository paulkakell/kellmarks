from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from site_defaults import SITE_RULES, site_host, suggest_tags


def test_local_rules_are_bounded_and_valid() -> None:
    import app as kellmarks

    for domain, tags in SITE_RULES.items():
        assert domain == site_host("https://" + domain)
        assert 0 < len(tags) <= 5
        assert tags == kellmarks.normalize_tags(tags)


@pytest.mark.parametrize("url, expected", [
    ("https://github.com/org/repo", ["development/git", "software/open-source"]),
    ("https://docs.python.org/3/", ["development/python"]),
    ("https://github.com.evil.test/path", ["sites/github.com.evil.test"]),
    ("https://notgithub.com/", ["sites/notgithub.com"]),
    ("http://www.EXAMPLE.test.:8080/a?q=private#secret", ["sites/example.test"]),
    ("https://bücher.example/", ["sites/xn--bcher-kva.example"]),
    ("http://[::1]:8787/", ["sites/::1"]),
])
def test_site_rules_and_host_boundaries(url, expected) -> None:
    assert suggest_tags(url, []) == expected


def test_suggestions_reuse_existing_same_host_tags_with_a_limit() -> None:
    entries = [
        {"url": "https://www.github.com/first", "tags": ["Team", "a", "b", "c", "d", "e"]},
        {"url": "https://github.com/second", "tags": ["team"]},
        {"url": "https://github.com.evil.test/", "tags": ["not-related"]},
    ]
    assert suggest_tags("https://github.com/third", entries) == ["Team", "a", "b", "c", "d"]
    assert suggest_tags("", []) == []
    assert len(suggest_tags("https://" + "a" * 50 + "." + "b" * 50 + ".test", [])[0]) == 80


@pytest.mark.parametrize("fields", [{}, {"tags": []}, {"tags": None}, {"tags": " , "}])
def test_create_populates_blank_tags_and_keeps_icon_optional(client, fields) -> None:
    response = client.post("/api/entries", json={"url": "https://python.org/", **fields})
    assert response.status_code == 201
    created = response.get_json()
    assert created["tags"] == ["development/python"]
    assert created["iconUrl"] == ""
    stored = client.get(f"/api/entries/{created['id']}").get_json()
    assert stored["tags"] == created["tags"]


def test_creation_only_preserves_manual_tags_and_clear_on_edit(client, monkeypatch) -> None:
    response = client.post("/api/entries", json={"url": "https://python.org/", "tags": ["Mine"]})
    created = response.get_json()
    assert created["tags"] == ["Mine"]
    inherited = client.post("/api/entries", json={"url": "https://www.python.org/new"}).get_json()
    assert inherited["tags"] == ["Mine"]

    def fail(*args, **kwargs):
        raise AssertionError("editing must never generate tags")

    monkeypatch.setattr("app.suggest_tags", fail)
    url = f"/api/entries/{created['id']}"
    assert client.put(url, json={"tags": []}).get_json()["tags"] == []
    assert client.put(url, json={"title": "Renamed"}).get_json()["tags"] == []
    assert client.put(url, json={"url": "https://github.com/new"}).get_json()["tags"] == []
    assert client.get(url).get_json()["tags"] == []


def test_import_and_reload_never_backfill_tags(client, monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("import/read must never generate tags")

    monkeypatch.setattr("app.suggest_tags", fail)
    entries = [{"id": "untagged", "url": "https://github.com/", "tags": []}]
    assert client.post("/api/import", json={"entries": entries}).status_code == 200
    assert client.get("/api/entries").get_json()[0]["tags"] == []
    preview = client.post("/api/import/preview", json={"entries": entries, "mode": "merge"})
    assert preview.status_code == 200
    assert client.get("/api/export").get_json()["entries"][0]["tags"] == []


def test_creation_suggestions_work_with_external_requests_denied(make_app) -> None:
    client = make_app(EXTERNAL_REQUESTS_ALLOWED=False).test_client()
    assert client.post("/api/entries", json={"url": "https://python.org/"}).get_json()["tags"] == ["development/python"]


def test_shared_browser_helpers() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", "--test", "tests/frontend_enhancements.test.cjs"], cwd=root,
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "# fail 0" in result.stdout
    assert json.loads((root / "docs/assets/site-tags.json").read_text()) == SITE_RULES
