from __future__ import annotations

import json
from pathlib import Path


def create_payload(url: str = "https://example.com") -> dict[str, object]:
    return {
        "title": "Example",
        "url": url,
        "iconUrl": "https://example.com/icon.png",
        "description": "Example bookmark",
        "tags": ["work/security", "reference"],
    }


def test_crud_lifecycle(client) -> None:
    created = client.post("/api/entries", json=create_payload())
    assert created.status_code == 201
    entry = created.get_json()
    assert entry["id"].startswith("e-")
    assert entry["url"] == "https://example.com"

    listed = client.get("/api/entries")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.get_json()] == [entry["id"]]

    fetched = client.get(f"/api/entries/{entry['id']}")
    assert fetched.status_code == 200
    assert fetched.get_json()["title"] == "Example"

    updated = client.put(
        f"/api/entries/{entry['id']}",
        json={"title": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.get_json()["title"] == "Updated"
    assert updated.get_json()["url"] == "https://example.com"

    deleted = client.delete(f"/api/entries/{entry['id']}")
    assert deleted.status_code == 200
    assert deleted.get_json()["deleted"] is True
    assert client.get(f"/api/entries/{entry['id']}").status_code == 404


def test_create_rejects_unsafe_urls_and_excessive_tags(client) -> None:
    unsafe = client.post("/api/entries", json=create_payload("javascript:alert(1)"))
    assert unsafe.status_code == 400

    payload = create_payload()
    payload["tags"] = [f"tag-{index}" for index in range(33)]
    too_many_tags = client.post("/api/entries", json=payload)
    assert too_many_tags.status_code == 400


def test_json_content_type_and_body_are_enforced(client) -> None:
    unsupported = client.post("/api/entries", data="{}", content_type="text/plain")
    assert unsupported.status_code == 415
    malformed = client.post(
        "/api/entries", data="{", content_type="application/json"
    )
    assert malformed.status_code == 400
    array_body = client.post("/api/entries", json=[])
    assert array_body.status_code == 400


def test_import_replaces_data_and_creates_backup(app, client) -> None:
    assert client.post("/api/entries", json=create_payload()).status_code == 201
    imported = client.post(
        "/api/import",
        json={
            "entries": [
                {
                    "id": "imported-one",
                    "title": "Imported",
                    "url": "https://import.example/",
                    "tags": ["imported"],
                }
            ]
        },
    )
    assert imported.status_code == 200
    assert imported.get_json() == {"backupCreated": True, "imported": 1}
    assert client.get("/api/entries").get_json()[0]["id"] == "imported-one"

    data_path = Path(app.config["DATA_PATH"])
    backup_path = data_path.with_suffix(data_path.suffix + ".bak")
    assert backup_path.exists()
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    assert backup["entries"][0]["title"] == "Example"


def test_import_rejects_unsafe_entries_without_changing_store(client) -> None:
    assert client.post("/api/entries", json=create_payload()).status_code == 201
    response = client.post(
        "/api/import",
        json={"entries": [{"id": "unsafe", "url": "javascript:alert(1)"}]},
    )
    assert response.status_code == 400
    assert len(client.get("/api/entries").get_json()) == 1


def test_request_size_limit(make_app) -> None:
    app = make_app(MAX_CONTENT_LENGTH=256)
    client = app.test_client()
    payload = create_payload()
    payload["description"] = "x" * 600
    response = client.post("/api/entries", json=payload)
    assert response.status_code == 413


def test_entry_and_import_limits(make_app) -> None:
    app = make_app(MAX_ENTRIES=1, MAX_IMPORT_ENTRIES=1)
    client = app.test_client()
    assert client.post("/api/entries", json=create_payload()).status_code == 201
    assert client.post("/api/entries", json=create_payload("https://two.example")).status_code == 400
    response = client.post(
        "/api/import",
        json={
            "entries": [
                {"id": "one", "url": "https://one.example"},
                {"id": "two", "url": "https://two.example"},
            ]
        },
    )
    assert response.status_code == 400


def test_search_and_tag_tree(client) -> None:
    assert client.post("/api/entries", json=create_payload()).status_code == 201
    assert client.post(
        "/api/entries",
        json={"title": "Personal", "url": "https://personal.example", "tags": []},
    ).status_code == 201

    search = client.get("/api/search", query_string={"q": "example AND security", "path": "work"})
    assert search.status_code == 200
    assert search.get_json()["count"] == 1

    tree = client.get("/api/tags/tree").get_json()
    assert tree["count"] == 2
    assert tree["children"]["work"]["children"]["security"]["count"] == 1
    assert tree["children"]["Untagged"]["count"] == 1


def test_query_length_limit(client) -> None:
    response = client.get("/api/search", query_string={"q": "x" * 513})
    assert response.status_code == 400


def test_export_contains_application_schema_version(client) -> None:
    response = client.get("/api/export")
    assert response.status_code == 200
    assert response.get_json()["version"] == 2
