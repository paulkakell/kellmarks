from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import Mock

import app as kellmarks
import pytest
import updates
from updates import MAX_RELEASE_BYTES, RELEASE_API, NoRedirects, ReleaseChecker, version_parts


class Reply(io.BytesIO):
    def geturl(self):
        return RELEASE_API


def release(tag="02.01.01", **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, **extra}


def mock_reply(monkeypatch, checker, data):
    raw = data if isinstance(data, bytes) else json.dumps(data).encode()
    opened = Mock(side_effect=lambda *a, **kw: Reply(raw))
    monkeypatch.setattr(checker._opener, "open", opened)
    return opened


@pytest.mark.parametrize("tag,expected", [
    ("02.01.01", "current"), ("v2.1.1", "current"), ("V02.01.01", "current"),
    ("02.02.00", "update_available"), ("v2.10.0", "update_available"),
    ("02.01.00", "ahead"), ("01.99.99", "ahead"),
])
def test_numeric_version_order_and_safe_release_link(monkeypatch, tag, expected) -> None:
    checker = ReleaseChecker("02.01.01")
    mock_reply(monkeypatch, checker, release(tag, html_url="https://untrusted.test/"))
    result = checker.check(allowed=True)
    assert result["status"] == expected
    assert result["currentVersion"] == "02.01.01"
    assert result["latestVersion"] == tag.lstrip("vV")
    assert result["releaseUrl"] == "https://github.com/paulkakell/kellmarks/releases/tag/" + tag
    assert result["checkedAt"].endswith("Z")


@pytest.mark.parametrize("data", [
    b"not JSON", b"\xff", [], None, {}, release("1.2.3-beta"), release("main"),
    release("1.2"), release("1.2.3/../../"), release(None),
    release(draft=True), release(prerelease=True),
    b"x" * (MAX_RELEASE_BYTES + 1),
])
def test_bad_release_data_never_claims_up_to_date(monkeypatch, data) -> None:
    checker = ReleaseChecker("02.01.01")
    mock_reply(monkeypatch, checker, data)
    result = checker.check(allowed=True)
    assert result["status"] == "unavailable" and result["latestVersion"] is None


@pytest.mark.parametrize("code,status", [(404, "no_release"), (403, "unavailable"), (429, "unavailable"), (500, "unavailable"), (302, "unavailable")])
def test_http_errors_and_missing_release(monkeypatch, code, status) -> None:
    checker = ReleaseChecker("02.01.01")
    opened = Mock(side_effect=urllib.error.HTTPError(RELEASE_API, code, "failure", {}, None))
    monkeypatch.setattr(checker._opener, "open", opened)
    assert checker.check(allowed=True)["status"] == status
    assert checker.check(allowed=True)["status"] == status
    assert opened.call_count == 1


def test_timeout_unexpected_url_and_no_redirects(monkeypatch) -> None:
    checker = ReleaseChecker("02.01.01")
    monkeypatch.setattr(checker._opener, "open", Mock(side_effect=TimeoutError()))
    assert checker.check(allowed=True)["status"] == "unavailable"
    checker = ReleaseChecker("02.01.01")
    reply = Reply(json.dumps(release()).encode())
    reply.geturl = lambda: "https://untrusted.test/"
    monkeypatch.setattr(checker._opener, "open", Mock(return_value=reply))
    assert checker.check(allowed=True)["status"] == "unavailable"
    assert NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://untrusted.test/") is None


def test_success_cache_and_operator_denial(monkeypatch) -> None:
    checker = ReleaseChecker("02.01.01")
    clock = [100.0]
    monkeypatch.setattr(updates.time, "monotonic", lambda: clock[0])
    opened = mock_reply(monkeypatch, checker, release())
    assert checker.check(allowed=False)["status"] == "disabled"
    assert opened.call_count == 0
    first = checker.check(allowed=True)
    first["status"] = "changed outside the cache"
    assert checker.check(allowed=True)["status"] == "current"
    assert checker.check(allowed=False)["checkedAt"] is None
    assert opened.call_count == 1
    clock[0] += updates.SUCCESS_TTL + 1
    assert checker.check(allowed=True)["status"] == "current"
    assert opened.call_count == 2


def test_failure_cache_expires(monkeypatch) -> None:
    checker = ReleaseChecker("02.01.01")
    clock = [100.0]
    monkeypatch.setattr(updates.time, "monotonic", lambda: clock[0])
    opened = mock_reply(monkeypatch, checker, b"broken")
    assert checker.check(allowed=True)["status"] == "unavailable"
    clock[0] += updates.FAILURE_TTL - 1
    checker.check(allowed=True)
    assert opened.call_count == 1
    clock[0] += 2
    checker.check(allowed=True)
    assert opened.call_count == 2


def test_endpoint_authentication_and_no_forwarded_secrets(make_app, monkeypatch) -> None:
    token = "a" * 40
    app = make_app(AUTH_TOKEN=token)
    checker = app.extensions["kellmarks_release_checker"]
    opened = mock_reply(monkeypatch, checker, release(kellmarks.APP_VERSION))
    client = app.test_client()
    assert client.get("/api/version").status_code == 401
    assert opened.call_count == 0
    response = client.get("/api/version", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 200 and response.get_json()["status"] == "current"
    assert response.headers["Cache-Control"] == "no-store"
    outbound = opened.call_args.args[0]
    assert outbound.full_url == RELEASE_API
    assert not outbound.has_header("Authorization")
    assert not outbound.has_header("Cookie")
    assert token not in str(outbound.header_items())
    assert opened.call_args.kwargs["timeout"] == 4


def test_denied_endpoint_and_health_have_no_network(make_app, monkeypatch) -> None:
    app = make_app(EXTERNAL_REQUESTS_ALLOWED=False)
    opened = Mock(side_effect=AssertionError("outbound request forbidden"))
    monkeypatch.setattr(app.extensions["kellmarks_release_checker"]._opener, "open", opened)
    client = app.test_client()
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/version").get_json()["status"] == "disabled"
    assert opened.call_count == 0


def test_version_parser_rejects_non_releases() -> None:
    assert version_parts("v02.10.00") == (2, 10, 0)
    with pytest.raises(ValueError):
        version_parts("02.01.00-rc1")
