# Kellmarks

[![Version 02.03.00](https://img.shields.io/badge/version-02.03.00-FFD700?style=flat-square&labelColor=000000)](docs/releases/02.03.00.md)
[![Latest release](https://img.shields.io/github/v/release/paulkakell/kellmarks?display_name=tag&sort=semver&style=flat-square&label=release)](https://github.com/paulkakell/kellmarks/releases/latest)
[![Python 3.10 and 3.13](https://img.shields.io/badge/python-3.10%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Data schema 2](https://img.shields.io/badge/data%20schema-2-FFD700?style=flat-square&labelColor=000000)](docs/API.md)
[![Security and quality](https://github.com/paulkakell/kellmarks/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/paulkakell/kellmarks/actions/workflows/ci.yml)
[![CodeQL](https://github.com/paulkakell/kellmarks/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/paulkakell/kellmarks/actions/workflows/codeql.yml)

Kellmarks is a local-first bookmark dashboard with hierarchical tags, Boolean search, import and export, and a small Flask API backed by one private JSON file.

Version: **02.03.00**

## Settings and description defaults

Use **Settings** for themes, import/export, remote icons and confirmed browser-memory
reset. Enable **Fill missing descriptions from linked sites for this session** to
populate blank descriptions on new saves from public HTML metadata. Manual text,
edits and imports are preserved. This is opt-in, server-only and disabled by the
operator's no-external-requests policy; failed lookups still save the bookmark.
See the [user guide](docs/USER_GUIDE.md) for limits and privacy.

## Prebuilt Docker installation (GHCR)

Use **`ghcr.io/paulkakell/kellmarks:02.03.00`** with the pull-only
`docker-compose.yml`. The image contains the dashboard, production API server
and private persistent storage support. Linux AMD64 and ARM64 are supported.
See the [complete GHCR installation guide](docs/GHCR_INSTALLATION.md) for downloading the files,
secure token generation, HTTPS, upgrades, backup/restore and registry access.
After creating `.env` as described there:

```bash
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d --wait
```

The existing `compose.yaml` remains the source-build option. Always name the
GHCR file explicitly when both files exist.

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

- Gold/black by default, with 22 theme presets including green and amber monochrome monitors, plus custom browser-local colors
- Click anywhere on a bookmark card to open its page; Edit, Delete and tag buttons retain their own actions
- Site favicon fallback with session-only remote-image consent
- Offline site-tag suggestions for new entries with blank tags; no automatic retagging on edit
- Footer release check with cached, privacy-preserving server lookup and explicit offline/disabled status
- Single-page bookmark dashboard
- Hierarchical tags using slash notation, such as `cloud/aws/iam`
- Boolean search with `AND`, `OR`, `NOT`, parentheses, and quoted phrases
- HTTP and HTTPS bookmark validation
- Protected JSON CRUD API
- Private, atomic file-backed persistence
- Reviewed JSON and browser bookmark HTML import, defaulting to merge
- Conservative duplicate review, field-source choices and stale-preview protection
- Explicit replacement with a private pre-import backup
- Title, recently added and recently updated sorting
- Library-only search by default; explicit web-search action
- Session-only remote-icon consent and an operator external-request switch
- Validated export; existing schema-2 API compatibility
- Optional DuckDuckGo Instant Answer proxy with response and rate limits
- Static demonstration with separate browser-local data; reviewed import requires Flask

## Roadmap and user guide

The [accepted project roadmap](docs/ROADMAP.md) covers all eleven feature areas, their dependencies and acceptance criteria. **02.01.00 implements the import/privacy/sorting foundation, not the entire roadmap.** Bulk editing, Trash/undo, capture, smart collections, reading workflow, notes, link health, offline synchronization and local AI are planned, not yet available.

See the [user guide](docs/USER_GUIDE.md) for merge versus replacement, duplicate choices, HTML folder mapping, privacy settings, sorting, recovery and limitations. Tracking: [issue #9](https://github.com/paulkakell/kellmarks/issues/9), [PR #10](https://github.com/paulkakell/kellmarks/pull/10).

## Installation options

| Option | Use case | Persistence |
| --- | --- | --- |
| **[Docker Compose full server](docs/INSTALLATION.md#docker-compose-full-server)** | Recommended server deployment: dashboard + API + production Gunicorn server | Private named Docker volume |
| **[Docker + HTTPS/Caddy](docs/INSTALLATION.md#https-full-server-with-caddy)** | Remote access with managed TLS certificates | Private library and certificate volumes |
| [Local Python](docs/INSTALLATION.md#local-python-installation) | Loopback-only personal use and development | Private JSON file |
| [Static demonstration](docs/INSTALLATION.md#static-demonstration) | Browser-local preview, not a shared server | Browser-local fallback storage |

**[Complete installation and operations guide](docs/INSTALLATION.md)** — prerequisites,
Linux/macOS/Windows setup, token generation, configuration, standalone Docker,
reverse proxies, upgrades, rollback, backup/restore, migration and troubleshooting.
Docker images are built from this repository; no prebuilt registry image is assumed.

Docker includes Python and all runtime dependencies. Local Python mode requires
Python 3.10 or newer. Node.js is only needed for development checks.
Runtime dependencies are pinned in `docs/server/requirements.lock`; Docker adds
pinned production-server dependencies from `docker/requirements.txt`.

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

Use the production [Docker HTTPS deployment](docs/INSTALLATION.md#https-full-server-with-caddy)
with the included Caddy overlay, or connect an
[existing HTTPS reverse proxy](docs/INSTALLATION.md#using-an-existing-reverse-proxy)
to the loopback-published Docker service. Do not run Flask's development server
as a production service. Bearer tokens must never traverse an untrusted plaintext
network; authentication, exact trusted hosts and public-origin validation remain
required. The full guide includes DNS, ports, certificate persistence and proxy
header configuration.

## Static demonstration mode

`docs/index.html` can be served without the Flask API. It loads only `docs/assets/sample-data.json` and uses browser-local fallback storage. Static mode is not shared persistence. The former public runtime file `docs/assets/data.json` was removed in 02.00.00.

## Disable application-owned external requests

```bash
export KELLMARKS_EXTERNAL_REQUESTS=0
python docs/server/app.py
```

This denies DuckDuckGo and automatic GitHub release checks before making an outbound request and disallows remote icon sources through the response security policy. The dashboard also disables those controls. Explicitly opening a saved website is still normal user-directed browser navigation. With the default value `1`, library searches remain local; the user must select **Search the web**, or opt into remote icons for the current page session. The footer independently checks only public Kellmarks release metadata through the server; no bookmark URLs or tokens are sent. Server operators and direct API clients remain trusted.

## Development checks

```bash
python -m pip install -r requirements-dev.txt
make validate
```

`make validate` runs compilation, JavaScript syntax validation, unit/integration/regression tests, coverage, Ruff, mypy, Bandit, the secret-pattern scan, pip-audit, release validation, and the performance budget.

Browser scenarios are a separate, pinned development dependency:

```bash
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
make browser
```

`make browser` launches isolated local stores, exercises the actual dashboard and mocks external search responses. It covers import cancellation, merge/replacement, stale previews, HTML safety, sorting, icon consent, favicon fallback, creation-only tags, all theme presets/custom persistence, version states, static mode, operator denial and mobile layout. Set `KELLMARKS_BROWSER_EXECUTABLE` only to use an already installed Chromium for testing. GitHub's quality gate installs browser dependencies and runs these scenarios in a clean environment.

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
