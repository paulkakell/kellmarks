# Kellmarks server 02.01.01

[![Version 02.01.01](https://img.shields.io/badge/version-02.01.01-FFD700?style=flat-square&labelColor=000000)](../releases/02.01.01.md)
[![Python 3.10 and 3.13](https://img.shields.io/badge/python-3.10%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Data schema 2](https://img.shields.io/badge/data%20schema-2-FFD700?style=flat-square&labelColor=000000)](../API.md)

The Flask server serves an explicit frontend allowlist and a protected JSON API. Runtime data is private and is not served by Flask.

## Installation options

For a complete production server, use the
[Docker Compose installation](../INSTALLATION.md#docker-compose-full-server).
It includes the dashboard, this API, Gunicorn, a private persistent volume,
authenticated health checks and non-root execution. The optional
[HTTPS/Caddy deployment](../INSTALLATION.md#https-full-server-with-caddy) adds TLS.
The [full installation guide](../INSTALLATION.md) also covers standalone Docker,
Windows, configuration, backups/restores, migration, upgrades and troubleshooting.

The commands below are the local Python/development alternative. Docker's fixed
container listener/data path and mandatory authentication are documented in the
[Docker configuration section](../INSTALLATION.md#configuration-and-storage).

## Install locally

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate       # Linux or macOS
# .venv\Scripts\activate        # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -r docs/server/requirements.txt
python docs/server/app.py
```

Open `http://127.0.0.1:8787`.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `KELLMARKS_BIND_HOST` | `127.0.0.1` | Flask development-server bind address. |
| `KELLMARKS_PORT` | `8787` | Listening port, from 1 through 65535. |
| `KELLMARKS_AUTH_TOKEN` | empty | Bearer token. When present, it protects all API clients. Minimum 32 characters. |
| `KELLMARKS_REQUIRE_AUTH` | `0` | Forces API authentication even for direct loopback requests. Requires a token. |
| `KELLMARKS_PUBLIC_ORIGIN` | empty | Exact public HTTP(S) origin used behind a TLS reverse proxy. Requires a token. |
| `KELLMARKS_ALLOWED_ORIGINS` | empty | Additional exact HTTP(S) origins permitted by CORS. `*` is rejected and a token is required. |
| `KELLMARKS_TRUSTED_HOSTS` | `localhost,127.0.0.1,[::1]` | Comma-separated exact hosts accepted by Flask. `*` is rejected. |
| `KELLMARKS_DATA_FILE` | `docs/server/instance/data.json` | Private persistent JSON file. |
| `KELLMARKS_LEGACY_DATA_FILE` | `docs/assets/data.json` | Optional legacy schema-1 file to validate and migrate on first start. |
| `KELLMARKS_ENABLE_HSTS` | `0` | Adds one-year HSTS. Enable only after HTTPS is consistently deployed. |
| `KELLMARKS_LOG_LEVEL` | `INFO` | Python log level. Logs are structured JSON. |
| `KELLMARKS_MAX_REQUEST_BYTES` | `1048576` | Maximum request body, 16 KiB through 16 MiB. |
| `KELLMARKS_MAX_DATA_BYTES` | `16777216` | Maximum persistent JSON size, 1 MiB through 256 MiB. |
| `KELLMARKS_MAX_ENTRIES` | `10000` | Maximum stored entries, 1 through 100000. |
| `KELLMARKS_MAX_IMPORT_ENTRIES` | `5000` | Maximum entries in one import, 1 through 100000. |
| `KELLMARKS_WRITE_RATE_LIMIT` | `120` | Write operations per client address per minute. |
| `KELLMARKS_DDG_RATE_LIMIT` | `30` | DuckDuckGo proxy requests per client address per minute. |
| `KELLMARKS_AUTH_RATE_LIMIT` | `20` | Failed authentication attempts per client address per minute. |

Boolean values accept `1`, `0`, `true`, `false`, `yes`, `no`, `on`, or `off`.

## Local protected example

```bash
export KELLMARKS_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export KELLMARKS_REQUIRE_AUTH=1
python docs/server/app.py
```

## HTTPS reverse-proxy deployment

Use the [production Docker HTTPS instructions](../INSTALLATION.md#https-full-server-with-caddy)
or [existing-proxy configuration](../INSTALLATION.md#using-an-existing-reverse-proxy).
The built-in Flask server is for local development, not production. Network
traffic must be protected by HTTPS (or a secure tunnel); the proxy must preserve
Host and remove client-supplied forwarding headers. Authentication is enforced
regardless of proxy headers. The application never trusts them for client identity.

## Cross-origin frontend

`KELLMARKS_PUBLIC_ORIGIN` handles the primary HTTPS frontend behind a proxy. For an additional separate frontend:

```bash
export KELLMARKS_ALLOWED_ORIGINS=https://bookmarks-ui.example.com
```

List exact origins only. Scheme and port are part of the origin. A bearer token is required whenever public or additional origins are configured.

## Data migration

On first 02.00.00 start:

1. If the private data file already exists, Kellmarks validates and uses it.
2. Otherwise, if the `KELLMARKS_LEGACY_DATA_FILE` path exists, Kellmarks validates it as legacy data.
3. A copy is saved as `data.pre-v02.00.00.json` beside the new private data file.
4. Normalized schema-version-2 data is atomically written to the private data file.
5. If no legacy data exists, `docs/assets/sample-data.json` seeds the private store.

Unsafe, malformed, corrupt, or oversized legacy data stops startup. It is never silently replaced.

Each successful import creates `data.json.bak` before replacing the current store.

## Storage requirements

- Place the private data file on a local filesystem that supports atomic rename and advisory locks.
- Run every writer with access to the same `.lock` file.
- Do not use multiple hosts against a shared network filesystem without validating its lock and rename semantics.
- Restrict the instance directory to the service account.
- Back up `data.json`, `data.json.bak`, and the pre-migration backup.

## Health check

```bash
curl --fail http://127.0.0.1:8787/api/health
```

When authentication is enabled:

```bash
curl --fail \
  -H "Authorization: Bearer ${KELLMARKS_AUTH_TOKEN}" \
  http://127.0.0.1:8787/api/health
```

## Logs

One JSON object is emitted per API request with timestamp, level, event, request ID, method, path, status, duration, and remote address. Query strings and authorization values are not logged by the application. Configure the reverse proxy with the same privacy standard.

## 02.01.01 reviewed imports and privacy

See [the user guide](../USER_GUIDE.md) and [accepted roadmap](../ROADMAP.md). The new `POST /api/import/preview` route validates a candidate without changing the store. Apply with an explicit `mode` and the returned `baseRevision`; `409` means the library changed and must be previewed again. The legacy no-mode import contract still means replacement. Schema 2 is unchanged.

Set `KELLMARKS_EXTERNAL_REQUESTS=0` to deny application-owned external requests and remote icons. The default `1` preserves direct API access, but the dashboard now needs an explicit web-search action or session icon consent. Restart the service and reload open dashboard pages after changing this operator setting. Do not interpret it as a firewall for user-directed navigation or unrelated processes.

Run `make browser` after installing `requirements-browser.txt` and Chromium. Browser tests use disposable stores and mocked external results, never the owner's live library. Retain the previous version source and copy both the private data file and its `.bak` before a downgrade or full restore.


## Dashboard defaults and release status

Version 02.01.01 fills empty tags only in the new-entry POST handler, using local site rules and existing same-host tags. Updates, imports and store reads do not generate tags. The frontend serves 20 browser-local theme presets plus custom colors and tries a site's HTTPS favicon only after remote-icon consent.

`GET /api/version` uses normal API authentication and a fixed public GitHub latest-release URL. No incoming token or bookmark data is forwarded; redirects are rejected, the response is bounded, and results are cached per process (one hour successful, five minutes unsuccessful). `KELLMARKS_EXTERNAL_REQUESTS=0` prevents that request and yields an explicit disabled status. Health checks do not contact GitHub. See [API details](../API.md) and [release notes](../releases/02.01.01.md).
