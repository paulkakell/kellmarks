# Changelog

All notable changes are recorded here. Kellmarks versions use `Release.Feature.BugFix` in fixed-width `xx.xx.xx` form.

## [02.00.00] - 2026-08-13

### Breaking

- **SEC-001:** Restricted the built-in development server to loopback addresses. Network deployment now requires an HTTPS reverse proxy or production WSGI boundary.
- **SEC-001:** API requests from non-loopback clients, reverse-proxy paths, or deployments with configured authentication now require `Authorization: Bearer <token>`.
- **SEC-001:** Removed wildcard CORS. Cross-origin access now requires an exact allowlist entry.
- **SEC-002:** Moved writable runtime data from the public `docs/assets/data.json` path to private `docs/server/instance/data.json` storage by default.
- **SEC-002:** Removed the catch-all static route and the tracked public runtime data file.
- Raised the supported Python minimum from 3.9 to 3.10.

### Added

- **SEC-001:** Added Trusted Host checks, public-origin validation, remote fail-closed behavior, public-Host and proxy-header protection, token length validation, and authentication throttling.
- **SEC-003:** Added common HTTP(S)-only validation for API writes, imports, icon URLs, static fallback imports, and DuckDuckGo results.
- **SEC-004:** Added cross-process locking, unique temporary files, `fsync`, atomic replacement, import backups, and corruption refusal.
- **SEC-005:** Added request, data-file, entry, import, tag, URL, internal-query, and external-query limits.
- **SEC-006:** Added write and external-search rate controls, bounded upstream responses, and trusted DuckDuckGo redirect validation.
- Added structured JSON request logs, validated request IDs, CSP, HSTS opt-in, and browser security headers.
- Added `VERSION`, release notes, security architecture, configuration examples, migration guidance, rollback instructions, and API security documentation.
- Added unit, integration, regression, concurrency, security, observability, and performance tests.
- Added Ruff, mypy, Bandit, pip-audit, secret scanning, release validation, CodeQL, Dependabot, and CI matrices for Python 3.10 and 3.13.
- Added fully pinned runtime and development dependency manifests.

### Fixed

- **SEC-003:** Prevented imported `javascript:`, `data:`, credential-bearing, malformed, and control-character URLs from reaching rendered links.
- **SEC-004:** Prevented concurrent writers from sharing one temporary filename and losing or corrupting the JSON store.
- Prevented invalid imports from partially replacing current data.
- Prevented sensitive runtime and server files from being served by Flask.
- Prevented API query values and bearer tokens from appearing in application logs.
- Corrected the frontend update notification so an edited entry reports `Updated` instead of `Added`.

### Dependencies

- Updated Flask from 3.0.3 to 3.1.3.
- Pinned direct and transitive runtime dependencies in `docs/server/requirements.lock`.
- Added pinned development security and quality tools in `requirements-dev.txt`.

### Compatibility

The entry JSON shape and documented endpoint paths remain compatible. Authentication, network binding, CORS, static routing, runtime data location, Python support, and several validation rules changed intentionally. See `docs/releases/02.00.00.md`.
