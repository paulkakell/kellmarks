from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import app as kellmarks
import pytest


def test_concurrent_mutations_preserve_every_entry(app) -> None:
    store = app.extensions["kellmarks_store"]

    def add_entry(index: int) -> None:
        def mutation(data):
            data["entries"].append(
                {
                    "id": f"thread-{index}",
                    "title": f"Thread {index}",
                    "url": f"https://example.com/{index}",
                    "iconUrl": "",
                    "description": "concurrency regression",
                    "tags": ["test/concurrency"],
                    "createdAt": kellmarks.utc_now_iso(),
                    "updatedAt": kellmarks.utc_now_iso(),
                }
            )

        store.mutate(mutation)

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(add_entry, range(80)))

    data = store.read()
    assert len(data["entries"]) == 80
    assert len({entry["id"] for entry in data["entries"]}) == 80
    persisted = json.loads(Path(app.config["DATA_PATH"]).read_text(encoding="utf-8"))
    assert len(persisted["entries"]) == 80


def test_unique_temporary_files_are_removed_after_write(app) -> None:
    store = app.extensions["kellmarks_store"]
    store.mutate(lambda data: data["entries"].append(
        {
            "id": "temporary-test",
            "title": "Temporary test",
            "url": "https://example.com/temp",
            "iconUrl": "",
            "description": "",
            "tags": [],
            "createdAt": kellmarks.utc_now_iso(),
            "updatedAt": kellmarks.utc_now_iso(),
        }
    ))
    data_path = Path(app.config["DATA_PATH"])
    assert list(data_path.parent.glob(f".{data_path.name}.*.tmp")) == []


def test_legacy_data_is_migrated_out_of_public_assets(make_app, tmp_path: Path) -> None:
    legacy = tmp_path / "legacy-data.json"
    data_path = tmp_path / "private" / "data.json"
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "id": "legacy",
                        "title": "Legacy",
                        "url": "https://legacy.example",
                        "tags": ["migration"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    app = make_app(
        DATA_PATH=data_path,
        LEGACY_DATA_PATH=legacy,
        SEED_PATH=tmp_path / "missing-seed.json",
    )
    store = app.extensions["kellmarks_store"]
    assert store.read()["entries"][0]["id"] == "legacy"
    assert data_path.exists()
    assert (data_path.parent / "data.pre-v02.00.00.json").exists()
    assert legacy.exists()


def test_invalid_legacy_data_fails_without_overwriting(make_app, tmp_path: Path) -> None:
    legacy = tmp_path / "unsafe-legacy.json"
    data_path = tmp_path / "private-invalid" / "data.json"
    legacy.write_text(
        json.dumps({"entries": [{"id": "unsafe", "url": "javascript:alert(1)"}]}),
        encoding="utf-8",
    )
    with pytest.raises(kellmarks.StoreError):
        make_app(
            DATA_PATH=data_path,
            LEGACY_DATA_PATH=legacy,
            SEED_PATH=tmp_path / "missing-seed.json",
        )
    assert not data_path.exists()


def test_corrupt_data_file_is_not_silently_reset(make_app, tmp_path: Path) -> None:
    data_path = tmp_path / "corrupt" / "data.json"
    data_path.parent.mkdir()
    data_path.write_text("not-json", encoding="utf-8")
    with pytest.raises(kellmarks.StoreError):
        make_app(DATA_PATH=data_path)
    assert data_path.read_text(encoding="utf-8") == "not-json"


def test_data_size_limit_is_enforced(make_app, tmp_path: Path) -> None:
    data_path = tmp_path / "oversize" / "data.json"
    data_path.parent.mkdir()
    data_path.write_text(" " * 2048, encoding="utf-8")
    with pytest.raises(kellmarks.StoreError, match="exceeds"):
        make_app(DATA_PATH=data_path, MAX_DATA_BYTES=1024)
