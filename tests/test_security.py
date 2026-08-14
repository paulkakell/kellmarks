from __future__ import annotations

TOKEN = "a" * 32


def test_remote_requests_fail_closed_without_token(client) -> None:
    response = client.get("/api/health", environ_base={"REMOTE_ADDR": "203.0.113.10"})
    assert response.status_code == 403
    assert "requires KELLMARKS_AUTH_TOKEN" in response.get_json()["error"]


def test_configured_token_protects_local_and_remote_requests(make_app) -> None:
    app = make_app(AUTH_TOKEN=TOKEN)
    client = app.test_client()
    assert client.get("/api/health").status_code == 401
    assert (
        client.get(
            "/api/health",
            headers={"Authorization": f"Bearer {TOKEN}"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        ).status_code
        == 200
    )


def test_forwarded_request_requires_auth_even_from_loopback(client) -> None:
    response = client.get(
        "/api/health",
        headers={"X-Forwarded-For": "203.0.113.10"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_authentication_is_rate_limited(make_app) -> None:
    app = make_app(AUTH_TOKEN=TOKEN, AUTH_RATE_LIMIT=1)
    client = app.test_client()
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health").status_code == 429


def test_cors_is_exact_and_never_wildcard(make_app) -> None:
    app = make_app(
        AUTH_TOKEN=TOKEN,
        ALLOWED_ORIGINS=frozenset({"https://ui.example"}),
    )
    client = app.test_client()
    authorized_headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Origin": "https://ui.example",
    }

    allowed = client.get("/api/health", headers=authorized_headers)
    assert allowed.status_code == 200
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://ui.example"
    assert allowed.headers["Access-Control-Allow-Origin"] != "*"

    rejected = client.get(
        "/api/health",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Origin": "https://evil.example",
        },
    )
    assert rejected.status_code == 403
    assert "Access-Control-Allow-Origin" not in rejected.headers


def test_preflight_allows_only_configured_origin(make_app) -> None:
    app = make_app(
        AUTH_TOKEN=TOKEN,
        ALLOWED_ORIGINS=frozenset({"https://ui.example"}),
    )
    client = app.test_client()
    response = client.options(
        "/api/entries",
        headers={
            "Origin": "https://ui.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://ui.example"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]


def test_untrusted_host_is_rejected(client) -> None:
    response = client.get("/api/health", headers={"Host": "evil.example"})
    assert response.status_code == 400


def test_security_headers_are_present(client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Request-ID"]


def test_hsts_is_opt_in(make_app) -> None:
    without_hsts = make_app().test_client().get("/api/health")
    assert "Strict-Transport-Security" not in without_hsts.headers
    with_hsts = make_app(ENABLE_HSTS=True).test_client().get("/api/health")
    assert "max-age=31536000" in with_hsts.headers["Strict-Transport-Security"]


def test_sensitive_runtime_files_are_not_static(client) -> None:
    paths = {
        "/assets/data.json": 404,
        "/server/app.py": 404,
        "/server/requirements.lock": 404,
        "/assets/sample-data.json": 200,
    }
    for path, expected_status in paths.items():
        response = client.get(path)
        try:
            assert response.status_code == expected_status
        finally:
            response.close()


def test_short_token_configuration_is_rejected(make_app) -> None:
    try:
        make_app(AUTH_TOKEN="too-short")
    except RuntimeError as error:
        assert "at least 32" in str(error)
    else:
        raise AssertionError("short authentication token was accepted")


def test_wildcard_trusted_host_configuration_is_rejected(make_app) -> None:
    try:
        make_app(TRUSTED_HOSTS=["*"])
    except RuntimeError as error:
        assert "invalid trusted host" in str(error)
    else:
        raise AssertionError("wildcard trusted host was accepted")


def test_wildcard_and_malformed_origin_configuration_is_rejected(make_app) -> None:
    for origin in ("*", "https://ui.example/path", "https://user@ui.example"):
        try:
            make_app(ALLOWED_ORIGINS=(origin,))
        except RuntimeError:
            continue
        raise AssertionError(f"unsafe allowed origin was accepted: {origin}")


def test_origin_header_with_path_is_rejected(make_app) -> None:
    app = make_app(
        AUTH_TOKEN=TOKEN,
        ALLOWED_ORIGINS=("https://ui.example",),
    )
    response = app.test_client().get(
        "/api/health",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Origin": "https://ui.example/path",
        },
    )
    assert response.status_code == 403


def test_token_with_whitespace_is_rejected(make_app) -> None:
    try:
        make_app(AUTH_TOKEN="a" * 31 + " ")
    except RuntimeError as error:
        assert "must not contain whitespace" in str(error)
    else:
        raise AssertionError("whitespace-bearing token was accepted")


def test_cross_origin_configuration_requires_authentication(make_app) -> None:
    try:
        make_app(ALLOWED_ORIGINS=("https://ui.example",))
    except RuntimeError as error:
        assert "requires KELLMARKS_AUTH_TOKEN" in str(error)
    else:
        raise AssertionError("cross-origin access was enabled without authentication")


def test_public_host_requires_authentication_even_through_loopback_proxy(make_app) -> None:
    app = make_app(TRUSTED_HOSTS=("bookmarks.example",))
    response = app.test_client().get(
        "/api/health",
        headers={"Host": "bookmarks.example"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 403


def test_public_origin_supports_https_reverse_proxy_without_trusting_headers(make_app) -> None:
    app = make_app(
        AUTH_TOKEN=TOKEN,
        REQUIRE_AUTH=True,
        PUBLIC_ORIGIN="https://bookmarks.example",
        TRUSTED_HOSTS=("bookmarks.example",),
    )
    response = app.test_client().get(
        "/api/health",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Host": "bookmarks.example",
            "Origin": "https://bookmarks.example",
        },
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://bookmarks.example"
