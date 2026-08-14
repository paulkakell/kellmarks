from __future__ import annotations

import app as kellmarks
import pytest


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,hello",
        "file:///etc/passwd",
        "https://user:password@example.com/",
        "https:///missing-host",
        "https://example.com/\nheader",
        "https://example.com/path with space",
        "https://example.com\\path",
        "https://example.com/%ZZ",
    ],
)
def test_normalize_http_url_rejects_unsafe_values(url: str) -> None:
    with pytest.raises(kellmarks.ValidationError):
        kellmarks.normalize_http_url(url)


def test_normalize_http_url_accepts_http_and_https() -> None:
    assert kellmarks.normalize_http_url("HTTPS://Example.COM/path?q=1") == (
        "https://example.com/path?q=1"
    )
    assert kellmarks.normalize_http_url("http://localhost:8787") == "http://localhost:8787"


def test_normalize_tags_deduplicates_and_limits_shape() -> None:
    assert kellmarks.normalize_tags([" work/security ", "WORK/security", "personal"]) == [
        "work/security",
        "personal",
    ]
    with pytest.raises(kellmarks.ValidationError):
        kellmarks.normalize_tags([f"tag-{index}" for index in range(33)])
    with pytest.raises(kellmarks.ValidationError):
        kellmarks.normalize_tags(["bad//path"])


def test_import_validation_rejects_duplicates_and_unsafe_urls() -> None:
    with pytest.raises(kellmarks.ValidationError, match="duplicate id"):
        kellmarks.normalize_import_entries(
            [
                {"id": "same", "url": "https://example.com/one"},
                {"id": "same", "url": "https://example.com/two"},
            ],
            10,
        )
    with pytest.raises(kellmarks.ValidationError, match="must use http or https"):
        kellmarks.normalize_import_entries(
            [{"id": "unsafe", "url": "javascript:alert(1)"}],
            10,
        )


def test_boolean_search_regression() -> None:
    entry = {
        "title": "AWS zero trust VPN",
        "url": "https://example.com",
        "description": "identity controls",
        "tags": ["work/security"],
    }
    assert kellmarks.matches_query(entry, 'vpn AND (aws OR azure)')
    assert kellmarks.matches_query(entry, '"zero trust" AND NOT azure')
    assert not kellmarks.matches_query(entry, "vpn AND azure")


def test_import_may_generate_missing_ids_but_persistent_store_may_not() -> None:
    imported = kellmarks.normalize_import_entries(
        [{"url": "https://example.com"}], 10
    )
    assert imported[0]["id"].startswith("e-")
    with pytest.raises(kellmarks.ValidationError, match="id is required"):
        kellmarks.normalize_store_object(
            {"entries": [{"url": "https://example.com"}]}, 10
        )
