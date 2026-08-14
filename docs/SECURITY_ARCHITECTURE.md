# Kellmarks Security Architecture

## Purpose

Kellmarks 02.00.00 is designed for one trusted owner, local-first operation, and controlled remote access. The primary assets are bookmark confidentiality, bookmark integrity, the bearer token, the private data file, and operational availability.

## Trust boundaries

```text
Browser
  | HTTPS or loopback HTTP
  v
Reverse proxy or direct Flask endpoint
  | exact Host, optional exact Origin, Bearer token
  v
Flask application
  | validated normalized data, process and file lock
  v
Private JSON store and backups

Flask application
  | fixed HTTPS endpoint, bounded response
  v
DuckDuckGo Instant Answer API
```

The browser and API are same-origin by default. CORS is closed unless exact origins are configured. Authentication uses an explicit bearer header rather than cookies. Runtime storage sits outside the served asset allowlist.

## Request security sequence

For each API request, Kellmarks:

1. validates or creates a request ID;
2. lets Flask validate the Host against `TRUSTED_HOSTS`;
3. validates an Origin when present;
4. handles an allowed preflight without a write;
5. determines whether authentication is required;
6. treats non-loopback addresses, non-loopback Host values, and proxy-forwarding headers as remote boundaries;
7. compares bearer tokens in constant time;
8. applies endpoint-specific rate and size limits;
9. validates and normalizes untrusted data;
10. performs the store transaction under a process and advisory filesystem lock;
11. adds security headers and structured request logging.

## Authentication model

- No token and direct loopback: API access is allowed for local development.
- Configured token: all API access requires that token.
- Non-loopback client or public Host without configured token: denied with `403`.
- Reverse-proxy header without configured token: denied with `403`.
- Invalid configured token: `401`, then `429` after the configured failure limit.

A reverse proxy connects from a local address in many deployments. Public Host values and forwarding headers already force authentication, while production proxy deployments must also set `KELLMARKS_AUTH_TOKEN`, `KELLMARKS_REQUIRE_AUTH=1`, and an exact `KELLMARKS_PUBLIC_ORIGIN`. The built-in server remains loopback-only.

## Authorization scope

Kellmarks has one owner role. A valid token can read, create, update, delete, import, export, search, and use the external-search proxy. There is no per-entry or multi-user authorization model. Use an identity-aware reverse proxy or extend the data model before operating as a shared untrusted service.

## Input validation

URLs are accepted only when they:

- use HTTP or HTTPS;
- include a host;
- do not include username or password components;
- contain no raw or percent-decoded control characters;
- fit the length limit;
- have a valid port and normalized IDNA or IP host.

The same validator covers create, update, import, icon URLs, migrated data, and external result URLs. Imports are all-or-nothing and reject duplicate IDs.

## Persistence design

The default runtime path is `docs/server/instance/data.json`, which is ignored by Git and is absent from the Flask static allowlist.

Every read-modify-write transaction:

1. acquires a process reentrant lock;
2. acquires an advisory lock on `data.json.lock`;
3. reads and validates the complete current store;
4. applies one mutation;
5. serializes and checks the final byte limit;
6. writes to a uniquely named temporary file in the same directory;
7. flushes and calls `fsync`;
8. restricts temporary-file permissions where supported;
9. atomically replaces the destination;
10. calls directory `fsync` on non-Windows platforms;
11. removes any residual temporary file;
12. releases the advisory and process locks.

A corrupt store is never silently reset. A successful import first copies the prior store to `.bak`.

## Static content boundary

Flask serves only:

- `/`
- `/favicon.ico`
- `/assets/app.css`
- `/assets/app.js`
- `/assets/logo.svg`
- `/assets/sample-data.json`

There is no catch-all route. Private data, server source, dependency files, lock files, and backups return `404`.

## Browser protections

Responses include CSP, frame denial, no-sniff, no-referrer, restrictive permissions, cross-origin isolation policies, no-store caching, and a request ID. HSTS is opt-in because enabling it on a non-HTTPS local host would be harmful.

The frontend constructs untrusted content with DOM APIs and `textContent`. It validates all rendered navigation URLs. The bearer token is kept in session storage, not local storage.

## External search boundary

The proxy builds the upstream URL internally and accepts only the user query. It requires HTTPS, confirms that the final response hostname remains within DuckDuckGo, limits the response to 2 MiB, parses strict UTF-8 JSON, validates output URLs, limits output count, and applies a per-process rate limit.

## Logging and observability

Application logs are newline-delimited JSON. The API request event contains:

- timestamp
- level
- event
- request ID
- HTTP method
- path without query string
- response status
- duration in milliseconds
- direct remote address

Authentication values and query-string values are excluded. Security denials have separate event names for monitoring. Edge proxy logs must be configured separately.

Suggested alerts:

- repeated `authentication_failed` or `remote_access_denied`
- `cors_rejected`
- `store_error`
- persistent `external_search_failed`
- elevated `429` responses
- health-check failures
- unexpected data-file growth

## Dependency and CI controls

Runtime and development dependencies are version-pinned. CI installs into a fresh environment, runs `pip check`, tests on Python 3.10 and 3.13, enforces branch coverage, checks JavaScript syntax, runs Ruff and mypy, executes Bandit and a repository secret-pattern scan, audits dependencies with pip-audit, validates release structure, runs a performance budget, starts the server for a smoke test, and runs CodeQL for Python and JavaScript. Dependabot targets the `dev` branch.

## Residual risks and scaling limits

- The rate limiter is process-local.
- A bearer token grants full owner access.
- Advisory locks depend on filesystem semantics and cooperating writers.
- The JSON data model reads the complete store for each operation.
- External icon URLs disclose the viewer's IP address to the icon host.
- A reverse proxy can still log sensitive bookmark URLs unless configured not to.

Use shared rate limiting, centralized identity, a database, icon proxying, and dedicated monitoring when those limits matter.
