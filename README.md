# Kellmarks

Kellmarks is a local-first bookmark dashboard with hierarchical tags, Boolean search, import and export, and a small Flask API backed by one private JSON file.

Version: **02.00.01**

## Security model

Version 02.00.00 changes the default trust model.

- The built-in development server is restricted to loopback addresses.
- Requests arriving from a non-loopback address are denied unless a bearer token is configured.
- A configured bearer token protects local requests too.
- Reverse-proxy headers force authentication so a proxy cannot make a remote request appear local.
- CORS is disabled unless exact origins are configured. Wildcards are rejected.
- Trusted Host validation is enabled. Wildcards are rejected.
- Runtime data is stored under `docs/server/instance/` by default and is never served as a static asset.
- Writes use a cross-process lock, unique temporary files, `fsync`, and atomic replacement.
- Imports, URLs, tags, requests, queries, and the persistent data file have explicit limits.
- API responses include restrictive browser security headers and structured request IDs.

See [SECURITY.md](SECURITY.md) and [docs/SECURITY_ARCHITECTURE.md](docs/SECURITY_ARCHITECTURE.md) before exposing the application through a network.

## Features

- Dark single-page bookmark dashboard
- Hierarchical tags using slash notation, such as `cloud/aws/iam`
- Boolean search with `AND`, `OR`, `NOT`, parentheses, and quoted phrases
- HTTP and HTTPS bookmark validation
- Protected JSON CRUD API
- Private, atomic file-backed persistence
- Validated import and export
- Optional DuckDuckGo Instant Answer proxy with response and rate limits
- Static read-only demonstration mode

## Requirements

- Python 3.10 or newer
- Node.js only for the JavaScript syntax check in CI

Runtime dependencies are fully pinned in `docs/server/requirements.lock`. Development and security tools are pinned in `requirements-dev.txt`.

## Local installation

```bash
python -m venv .venv
source .venv/bin/activate       # Linux or macOS
# .venv\Scripts\activate        # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r docs/server/requirements.txt
python docs/server/app.py
```

Open `http://127.0.0.1:8787`.

Local loopback requests do not require a token unless `KELLMARKS_AUTH_TOKEN` or `KELLMARKS_REQUIRE_AUTH=1` is set.

## Protected local mode

Generate a token rather than writing one by hand:

```bash
export KELLMARKS_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export KELLMARKS_REQUIRE_AUTH=1
python docs/server/app.py
```

The browser asks for the token and retains it in `sessionStorage` for the current browser session. The token is not placed in URLs or local storage.

## HTTPS reverse-proxy mode

Keep the built-in server on loopback and terminate HTTPS at a maintained reverse proxy:

```bash
export KELLMARKS_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export KELLMARKS_REQUIRE_AUTH=1
export KELLMARKS_TRUSTED_HOSTS=bookmarks.example.com
export KELLMARKS_PUBLIC_ORIGIN=https://bookmarks.example.com
export KELLMARKS_ENABLE_HSTS=1
python docs/server/app.py
```

Configure the proxy to preserve `Host`, forward `https://bookmarks.example.com` to `http://127.0.0.1:8787`, remove client-supplied forwarding headers before setting its own, and avoid logging authorization values or URL query strings. The application does not trust forwarding headers for client identity.

A production WSGI server may bind inside an isolated container or private network, but TLS must terminate before untrusted traffic reaches it. Bearer tokens must never traverse an untrusted plaintext network. Do not place the token in a query string, cookie, log field, image URL, or repository file.

## Static demonstration mode

`docs/index.html` can be served without the Flask API. It loads only `docs/assets/sample-data.json` and uses browser-local fallback storage. Static mode is not shared persistence. The former public runtime file `docs/assets/data.json` was removed in 02.00.00.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
make validate
```

`make validate` runs compilation, JavaScript syntax validation, unit/integration/regression tests, coverage, Ruff, mypy, Bandit, the secret-pattern scan, pip-audit, release validation, and the performance budget.

GitHub Actions repeats the suite on Python 3.10 and 3.13 and runs CodeQL for Python and JavaScript.

## Repository layout

```text
.
├── VERSION
├── CHANGELOG.md
├── SECURITY.md
├── requirements-dev.txt
├── pyproject.toml
├── tests/
├── scripts/
└── docs/
    ├── index.html
    ├── API.md
    ├── openapi.yaml
    ├── SECURITY_ARCHITECTURE.md
    ├── assets/
    │   ├── app.js
    │   ├── app.css
    │   └── sample-data.json
    └── server/
        ├── app.py
        ├── requirements.lock
        └── instance/          # ignored private runtime data
```

## Upgrade from 01.xx.xx

Back up any existing `docs/assets/data.json` before switching branches. On first start, 02.00.00 validates that legacy file, copies a pre-migration backup into the private instance directory, and writes schema version 2 to the new private location. Set `KELLMARKS_LEGACY_DATA_FILE` when the backup is stored elsewhere. Invalid or unsafe legacy data stops startup rather than being discarded.

Detailed migration and rollback procedures are in [the 02.00.00 release notes](docs/releases/02.00.00.md).

## API

The OpenAPI document is at [docs/openapi.yaml](docs/openapi.yaml), with practical examples in [docs/API.md](docs/API.md).

## License

Unlicense.
