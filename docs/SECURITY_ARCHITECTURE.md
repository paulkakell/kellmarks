# Kellmarks Security Architecture

## Purpose

Kellmarks 02.01.01 is designed for one trusted owner, local-first operation, and controlled remote access. The primary assets are bookmark confidentiality, bookmark integrity, the bearer token, the private data file, and operational availability.

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
  | operator external-request policy, explicit user action
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
- `/assets/enhancements.js`
- `/assets/site-tags.json`
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

## Reviewed import boundary in 02.01.00

```text
Untrusted JSON or browser bookmark HTML
  | request byte limit, authenticated/rate-limited preview
  v
Text-only HTML parser / entry validation
  | conservative identity, explicit field choices, validated final limits
  v
Read-only candidate + revision of existing entries
  | explicit Apply, same lock, revision comparison
  v
Private backup -> fsync + atomic replacement
```

`docs/server/importing.py` has no networking. HTML is parsed as text, not inserted into a document, and script/style/resource attributes are not executed or fetched. Folder nesting is capped at 32 and normal entry/tag/URL constraints still apply. Invalid imports are not partially applied. Duplicate identity does not discard query parameters, fragments or meaningful path distinctions. Import-wide field preferences never overwrite existing URL, ID, creation time or icon.

The revision is a concurrency check, not an authentication token or a signature approving particular imported content. Every apply is revalidated under the same cross-process lock. Authenticated clients already have full mutation privileges. The old no-mode replacement API remains intentionally available for compatibility and lacks the new preview guard; the dashboard never uses it for reviewed imports.

The preview response may contain bookmark URLs and normalized content. It has the same authentication, no-store policy and request-ID logging as other private APIs. Logs contain paths and outcomes, not imported data, titles, query strings, preview revisions or credentials. The UI reports uncertain/failed requests without claiming that a commit definitely did not happen.

`KELLMARKS_EXTERNAL_REQUESTS=0` denies DDG before opening an upstream connection and removes remote sources from `img-src`. The dashboard fails closed when the health capability is absent. Remote icon consent lives only in page memory and resets on reload. Disabling icons stops future application-created image loads; it cannot undo requests already sent. Operator setting changes require restart and open-page reload. The switch is not a system-wide egress firewall and does not block explicit navigation to a saved website. Future metadata, health, preservation and AI routes must implement the same central policy; those routes do not exist in this release.

No authentication or authorization model is widened; no arbitrary server-side URL fetching is added; no runtime dependency is changed. Browser-test dependencies are separate development-only tools and receive their own CI audit. Whole-library backups remain a single rolling `.bak`, not the future multi-snapshot recovery or Trash feature. Keep independent copies before replacing the backup or restoring.


## 02.01.01 dashboard egress and local preferences

Favicon fallback is computed in the browser from the bookmark origin only, using HTTPS `/favicon.ico`. It never sends saved paths, queries or fragments to an icon service, and it does not add arbitrary URL fetching to the server. The existing session-only image opt-in, image security policy and operator denial continue to apply; failed loads show initials. As with explicit remote icons, contacting a site reveals the browser's network address and may be subject to normal browser cookie behavior.

Site-tag suggestions are local, bounded and creation-only. They reuse validated stored tags, bundled site rules or a normalized hostname. No metadata scraping, external classification service or AI model is involved. Imported or existing data is not implicitly rewritten.

Theme preferences are browser-local, not secrets or shared-store fields. Only the five expected six-digit hex color values and known preset identifiers are accepted. CSS URLs and arbitrary style properties are not accepted. Invalid storage falls back to gold/black; storage exceptions do not prevent app initialization. Custom contrast warnings do not impose a forced palette.

The footer adds one automatic, server-side egress path: the fixed public GitHub latest-release endpoint for this repository. Normal API authorization gates `/api/version`. Incoming tokens, cookies and bookmark data are never forwarded. Redirects are rejected before following their targets; a four-second socket timeout and 256 KiB read limit bound requests. A process-local lock and one-hour success/five-minute failure cache limit upstream traffic. This is a status check, not an updater. All failures remain explicit rather than falsely asserting that software is current. `KELLMARKS_EXTERNAL_REQUESTS=0` short-circuits the lookup, and health checks do not fetch releases. Static mode does not bypass the same-origin connection policy to contact GitHub directly.
