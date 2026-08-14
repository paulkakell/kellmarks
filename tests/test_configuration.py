from __future__ import annotations

from datetime import datetime, timezone

import app as kellmarks
import pytest


def test_environment_boolean_parsing(monkeypatch) -> None:
    monkeypatch.delenv("BOOL_SETTING", raising=False)
    assert kellmarks._env_bool("BOOL_SETTING", True) is True
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("BOOL_SETTING", value)
        assert kellmarks._env_bool("BOOL_SETTING") is True
    for value in ("0", "false", "NO", "off"):
        monkeypatch.setenv("BOOL_SETTING", value)
        assert kellmarks._env_bool("BOOL_SETTING", True) is False
    monkeypatch.setenv("BOOL_SETTING", "sometimes")
    with pytest.raises(RuntimeError, match="boolean"):
        kellmarks._env_bool("BOOL_SETTING")


def test_environment_integer_and_csv_parsing(monkeypatch) -> None:
    monkeypatch.delenv("INT_SETTING", raising=False)
    assert kellmarks._env_int("INT_SETTING", 5, 1, 10) == 5
    monkeypatch.setenv("INT_SETTING", "7")
    assert kellmarks._env_int("INT_SETTING", 5, 1, 10) == 7
    monkeypatch.setenv("INT_SETTING", "seven")
    with pytest.raises(RuntimeError, match="integer"):
        kellmarks._env_int("INT_SETTING", 5, 1, 10)
    monkeypatch.setenv("INT_SETTING", "11")
    with pytest.raises(RuntimeError, match="between"):
        kellmarks._env_int("INT_SETTING", 5, 1, 10)

    monkeypatch.delenv("CSV_SETTING", raising=False)
    assert kellmarks._env_csv("CSV_SETTING", ("default",)) == ("default",)
    monkeypatch.setenv("CSV_SETTING", "one, two, ,three")
    assert kellmarks._env_csv("CSV_SETTING") == ("one", "two", "three")


def test_text_validation_covers_type_required_length_and_controls() -> None:
    assert kellmarks._require_text(None, "field", 10) == ""
    with pytest.raises(kellmarks.ValidationError, match="string"):
        kellmarks._require_text(7, "field", 10)
    with pytest.raises(kellmarks.ValidationError, match="required"):
        kellmarks._require_text("  ", "field", 10, required=True)
    with pytest.raises(kellmarks.ValidationError, match="exceed"):
        kellmarks._require_text("eleven chars", "field", 10)
    with pytest.raises(kellmarks.ValidationError, match="control"):
        kellmarks._require_text("line%0Abreak", "field", 20)


def test_url_validation_covers_optional_ipv6_idna_and_syntax_errors() -> None:
    assert kellmarks.normalize_http_url("", required=False) == ""
    assert kellmarks.normalize_http_url("https://[2001:db8::1]:8443/path") == (
        "https://[2001:db8::1]:8443/path"
    )
    assert kellmarks.normalize_http_url("https://BÜCHER.example/") == (
        "https://xn--bcher-kva.example/"
    )
    for value, message in (
        ("https://example.com/a b", "whitespace"),
        ("https://example.com/%zz", "percent"),
        ("https://example.com:99999", "valid URL"),
    ):
        with pytest.raises(kellmarks.ValidationError, match=message):
            kellmarks.normalize_http_url(value)


def test_tag_validation_covers_supported_shapes_and_edges() -> None:
    assert kellmarks.normalize_tags(None) == []
    assert kellmarks.normalize_tags("work/security, personal, ") == [
        "work/security",
        "personal",
    ]
    with pytest.raises(kellmarks.ValidationError, match="list of strings"):
        kellmarks.normalize_tags({"not": "a tag list"})
    with pytest.raises(kellmarks.ValidationError, match="exceed"):
        kellmarks.normalize_tags(["x" * 81])


def test_timestamp_normalization_uses_safe_fallback_and_utc() -> None:
    fallback = "2026-08-13T00:00:00Z"
    assert kellmarks.normalize_timestamp(None, fallback) == fallback
    assert kellmarks.normalize_timestamp("not-a-date", fallback) == fallback
    assert kellmarks.normalize_timestamp("2026-08-13T12:30:00", fallback) == (
        "2026-08-13T12:30:00Z"
    )
    offset = kellmarks.normalize_timestamp("2026-08-13T12:30:00-06:00", fallback)
    assert datetime.fromisoformat(offset.replace("Z", "+00:00")).tzinfo == timezone.utc


def test_entry_id_and_payload_validation_cover_generation_and_errors() -> None:
    generated = kellmarks.normalize_entry_id(None, generate=True)
    assert generated.startswith("e-")
    with pytest.raises(kellmarks.ValidationError, match="id is required"):
        kellmarks.normalize_entry_id(None)
    with pytest.raises(kellmarks.ValidationError, match="unsupported"):
        kellmarks.normalize_entry_id("bad id")
    with pytest.raises(kellmarks.ValidationError, match="JSON object"):
        kellmarks.normalize_entry_payload([])


def test_import_and_store_root_validation_covers_invalid_shapes() -> None:
    with pytest.raises(kellmarks.ValidationError, match="entries must be a list"):
        kellmarks.normalize_import_entries({}, 5)
    with pytest.raises(kellmarks.ValidationError, match="no more than"):
        kellmarks.normalize_import_entries([{}, {}], 1)
    with pytest.raises(kellmarks.ValidationError, match=r"entries\[0\] must be an object"):
        kellmarks.normalize_import_entries(["invalid"], 5)

    entry = {
        "id": "one",
        "title": "One",
        "url": "https://one.example",
        "tags": [],
    }
    normalized_list = kellmarks.normalize_store_object([entry], 5)
    assert normalized_list["version"] == 2
    assert normalized_list["entries"][0]["id"] == "one"
    with pytest.raises(kellmarks.StoreError, match="contain entries"):
        kellmarks.normalize_store_object({}, 5)
    with pytest.raises(kellmarks.StoreError, match="object or list"):
        kellmarks.normalize_store_object("invalid", 5)
