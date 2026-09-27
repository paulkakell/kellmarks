from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import app as kellmarks
import pytest
from importing import (
    ImportProblem,
    build_import_plan,
    duplicate_key,
    import_options,
    library_revision,
    parse_bookmark_html,
)


def entry(url="https://example.com", **fields):
    return {"url": url, "title": "Imported", **fields}


def preview(client, entries=None, **options):
    return client.post("/api/import/preview", json={"entries": entries or [], **options})


def apply_preview(client, review, **options):
    return client.post("/api/import", json={
        "mode": review["mode"], "entries": review["incomingEntries"],
        "baseRevision": review["baseRevision"], **options,
    })


def test_preview_merge_backup_and_legacy_rollback(client, app):
    original = client.post("/api/entries", json=entry(tags=["work"])).json
    store = app.extensions["kellmarks_store"]
    before = store.data_path.read_bytes()
    response = preview(client, [entry(tags=["WORK", "research"]), entry("https://other.test")])
    assert response.status_code == 200
    review = response.json
    assert review["valid"] and review["mode"] == "merge"
    assert (review["newCount"], review["updatedCount"], review["duplicateCount"]) == (1, 1, 1)
    assert review["totalCount"] == 2
    assert store.data_path.read_bytes() == before
    assert not store.data_path.with_suffix(".json.bak").exists()
    applied = apply_preview(client, review)
    assert applied.status_code == 200
    assert applied.json["backupCreated"] is True
    assert applied.json["added"] == applied.json["updated"] == 1
    current = client.get("/api/entries").json
    assert current[0]["id"] == original["id"]
    assert current[0]["createdAt"] == original["createdAt"]
    assert current[0]["url"] == original["url"]
    assert current[0]["tags"] == ["work", "research"]
    backup = store.data_path.with_suffix(".json.bak").read_bytes()
    assert backup == before
    # A schema-2 backup still restores through the legacy API contract.
    restored = client.post("/api/import", json=json.loads(backup))
    assert restored.json == {"imported": 1, "backupCreated": True}
    assert client.get("/api/entries").json == [original]


def test_duplicate_choices_retained_originals_and_unchanged(client):
    original = client.post("/api/entries", json=entry(
        title="Original", description="Original note", iconUrl="https://example.com/icon.png"
    )).json
    review = preview(client, [entry(description="Incoming note")]).json
    assert review["unchangedCount"] == 1
    assert review["updatedCount"] == 0
    apply_preview(client, review)
    assert client.get("/api/entries").json == [original]
    choices = {"titleSource": "incoming", "descriptionSource": "incoming"}
    review = preview(client, [entry("https://EXAMPLE.com:443/", description="Incoming note")], **choices).json
    assert review["updatedCount"] == 1
    assert apply_preview(client, review, **choices).status_code == 200
    current = client.get("/api/entries").json[0]
    assert current["title"] == "Imported" and current["description"] == "Incoming note"
    assert all(current[field] == original[field] for field in ("id", "createdAt", "url", "iconUrl"))
    # An empty incoming note never erases a useful existing note.
    review = preview(client, [entry(description="")], **choices).json
    apply_preview(client, review, **choices)
    assert client.get("/api/entries").json[0]["description"] == "Incoming note"


def test_replace_is_explicit_and_accepts_empty_library(client):
    client.post("/api/entries", json=entry())
    review = preview(client, [], mode="replace").json
    assert review["replacedCount"] == 1 and review["totalCount"] == 0
    assert apply_preview(client, review).status_code == 200
    assert client.get("/api/entries").json == []


def test_stale_preview_never_overwrites_concurrent_change(client, app):
    review = preview(client, [entry()]).json
    client.post("/api/entries", json=entry("https://concurrent.test"))
    before = Path(app.config["DATA_PATH"]).read_bytes()
    response = apply_preview(client, review)
    assert response.status_code == 409
    assert "preview" in response.json["error"]
    assert Path(app.config["DATA_PATH"]).read_bytes() == before
    assert len(client.get("/api/entries").json) == 1


@pytest.mark.parametrize("revision", [None, "", "bad", 42, {}, "A" * 64])
def test_apply_requires_valid_revision(client, revision):
    response = client.post("/api/import", json={
        "entries": [entry()], "mode": "merge", "baseRevision": revision,
    })
    assert response.status_code == 400
    assert client.get("/api/entries").json == []


def test_invalid_entries_and_duplicate_ids_are_previewed_without_writes(client, app):
    before = Path(app.config["DATA_PATH"]).read_bytes()
    review = preview(client, [entry(id="same"), entry(id="same"),
                              entry("javascript:alert(1)"), None]).json
    assert review["valid"] is False and review["invalidCount"] == 3
    assert [error["index"] for error in review["errors"]] == [1, 2, 3]
    assert review["incomingEntries"] == []
    assert Path(app.config["DATA_PATH"]).read_bytes() == before
    assert preview(client, [None] * 60).json["invalidCount"] == 60
    assert len(preview(client, [None] * 60).json["errors"]) == 50


def test_conflicting_existing_ids_and_ambiguous_urls(client):
    first = client.post("/api/entries", json=entry()).json
    response = preview(client, [entry("https://different.test", id=first["id"])])
    assert response.status_code == 400
    assert "different URL" in response.json["error"]
    client.post("/api/entries", json=entry("https://example.com:443/"))
    response = preview(client, [entry()])
    assert response.status_code == 400
    assert "multiple existing" in response.json["error"]
    assert len(client.get("/api/entries").json) == 2


def test_import_limits_and_candidate_size(make_app):
    application = make_app(MAX_IMPORT_ENTRIES=1, MAX_ENTRIES=1)
    client = application.test_client()
    assert preview(client, [entry(), entry("https://other.test")]).status_code == 400
    client.post("/api/entries", json=entry(tags=[f"t{i}" for i in range(32)]))
    assert preview(client, [entry(tags=["extra"])]).status_code == 400
    assert preview(client, [entry("https://other.test")]).status_code == 400
    store = application.extensions["kellmarks_store"]
    store.max_entries = 10
    store.max_data_bytes = 1
    # Candidate validation runs before backup creation or a live-store write.
    store._read_unlocked = lambda: {"entries": [], "version": 2}
    with pytest.raises(ImportProblem, match="data size"):
        store.reviewed_import(kellmarks.normalize_import_entries([entry()], 1),
                              mode="merge", title_source="existing", description_source="existing")


@pytest.mark.parametrize("payload", [
    {"format": "xml", "entries": []}, {"entries": None}, {"entries": {}},
    {"mode": "invalid", "entries": []}, {"mode": [], "entries": []},
    {"titleSource": {}, "entries": []}, {"descriptionSource": False, "entries": []},
])
def test_invalid_source_and_options_return_400(client, payload):
    assert client.post("/api/import/preview", json=payload).status_code == 400


def test_import_preview_authentication_content_type_and_rate_limit(make_app):
    protected = make_app(AUTH_TOKEN="x" * 40).test_client()
    assert preview(protected, [entry()]).status_code == 401
    local = make_app(WRITE_RATE_LIMIT=1).test_client()
    assert preview(local, [entry()]).status_code == 200
    assert preview(local, [entry()]).status_code == 429
    ordinary = make_app().test_client()
    assert ordinary.post("/api/import/preview", data="[]", content_type="text/plain").status_code == 415
    assert ordinary.post("/api/import/preview", json=[]).status_code == 400


def test_failed_backup_or_write_keeps_live_library(client, app, monkeypatch):
    client.post("/api/entries", json=entry())
    store = app.extensions["kellmarks_store"]
    before = store.data_path.read_bytes()
    review = preview(client, [entry("https://another.test")]).json

    def fail(*args, **kwargs):
        raise kellmarks.StoreError("simulated failure")

    with monkeypatch.context() as context:
        context.setattr(kellmarks, "atomic_private_copy", fail)
        assert apply_preview(client, review).status_code == 500
    assert store.data_path.read_bytes() == before
    with monkeypatch.context() as context:
        context.setattr(store, "_write_unlocked", fail)
        assert apply_preview(client, review).status_code == 500
    assert store.data_path.read_bytes() == before
    assert store.data_path.with_suffix(".json.bak").read_bytes() == before


def test_browser_html_folders_entities_descriptions_and_no_fetch(client, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Import must never fetch a URL")

    monkeypatch.setattr(kellmarks.urllib.request, "urlopen", deny)
    html = '''<!DOCTYPE NETSCAPE-Bookmark-file-1>
    <DL><p><DT><H3>Work</H3><DL><DT><H3>AWS/100%</H3><DL>
    <DT><A HREF="https://example.com?q=one&amp;x=two">A &amp; B<script>bad</script></A>
    <DD>Useful <b>research</b> <img src="https://tracking.test">
    </DL></DL><DT><A HREF="https://other.test">Other</A></DL>'''
    response = client.post("/api/import/preview", json={"format": "html", "html": html})
    assert response.status_code == 200
    review = response.json
    first = review["incomingEntries"][0]
    assert first["url"] == "https://example.com?q=one&x=two"
    assert first["title"] == "A & B"
    assert first["description"] == "Useful research"
    assert first["tags"] == ["Work/AWS%2F100%25"]
    assert review["incomingEntries"][1]["tags"] == []
    assert apply_preview(client, review).status_code == 200
    assert len(client.get("/api/entries").json) == 2


@pytest.mark.parametrize("html", [None, "", "   ", "<h1>No bookmarks</h1>", 123])
def test_invalid_html_is_rejected(html):
    with pytest.raises(ImportProblem):
        parse_bookmark_html(html, 10)


def test_html_limits_missing_href_and_tolerant_endings(client):
    with pytest.raises(ImportProblem, match="nesting"):
        parse_bookmark_html("<dl>" * 33, 100)
    with pytest.raises(ImportProblem, match="bookmarks"):
        parse_bookmark_html('<a href="https://a.test">A</a>' * 2, 1)
    assert parse_bookmark_html('<a href="https://a.test">A', 1)[0]["title"] == "A"
    assert parse_bookmark_html('<dl><style>ignore</style><a href="https://a.test"></a></dl></dl>', 1)[0]["title"] == "https://a.test"
    response = client.post("/api/import/preview", json={"format": "html", "html": "<a>No href</a>"})
    assert response.json["invalidCount"] == 1


@pytest.mark.parametrize("left,right,equal", [
    ("https://example.com", "https://EXAMPLE.com:443/", True),
    ("http://example.com:80", "http://example.com/", True),
    ("https://[::1]:443", "https://[::1]/", True),
    ("https://example.com:8443", "https://example.com", False),
    ("http://example.com", "https://example.com", False),
    ("https://example.com/a", "https://example.com/A", False),
    ("https://example.com/a", "https://example.com/a/", False),
    ("https://example.com/?id=1", "https://example.com/?id=2", False),
    ("https://example.com/#one", "https://example.com/#two", False),
])
def test_conservative_duplicate_identity(left, right, equal):
    assert (duplicate_key(left) == duplicate_key(right)) is equal


def test_plan_is_pure_and_combines_duplicates_inside_file():
    values = kellmarks.normalize_import_entries([entry(tags=["a"]), entry(tags=["b"])], 2)
    before = deepcopy(values)
    result, summary = build_import_plan([], values, mode="merge", title_source="incoming",
                                        description_source="incoming", now="2026-09-27T00:00:00Z")
    assert values == before
    assert len(result) == 1 and result[0]["tags"] == ["a", "b"]
    assert summary["newCount"] == 1 and summary["duplicateCount"] == 1
    assert library_revision(before) == library_revision(deepcopy(before))
    assert library_revision(result) != library_revision(before)
    assert import_options({}) == ("merge", "existing", "existing")


def test_operator_privacy_denial_precedes_outbound_call(make_app, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("No outbound request permitted")

    monkeypatch.setattr(kellmarks.urllib.request, "urlopen", deny)
    private = make_app(EXTERNAL_REQUESTS_ALLOWED=False).test_client()
    health = private.get("/api/health")
    assert health.json["externalRequestsAllowed"] is False
    assert "img-src 'self' data:;" in health.headers["Content-Security-Policy"]
    assert private.get("/api/external/ddg?q=confidential").status_code == 403
    assert private.get("/api/external/ddg").status_code == 403
    enabled = make_app().test_client().get("/api/health")
    assert enabled.json["externalRequestsAllowed"] is True
    assert "img-src 'self' https: data:;" in enabled.headers["Content-Security-Policy"]


def test_external_request_environment_is_validated(monkeypatch, make_app):
    monkeypatch.setenv("KELLMARKS_EXTERNAL_REQUESTS", "0")
    assert make_app().test_client().get("/api/health").json["externalRequestsAllowed"] is False
    monkeypatch.setenv("KELLMARKS_EXTERNAL_REQUESTS", "maybe")
    with pytest.raises(RuntimeError, match="boolean"):
        make_app()


def test_id_collision_is_rejected_even_when_url_matches_another_entry(client):
    first = client.post("/api/entries", json=entry()).json
    client.post("/api/entries", json=entry("https://another.test"))
    response = preview(client, [entry("https://another.test", id=first["id"])])
    assert response.status_code == 400
    assert "different URL" in response.json["error"]
    assert len(client.get("/api/entries").json) == 2
