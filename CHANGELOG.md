# Changelog

All notable changes are recorded here. Kellmarks versions use `Release.Feature.BugFix` in fixed-width `xx.xx.xx` form.

## [02.00.02] - 2026-08-13

### Fixed

- **REL-002:** Synchronized the current release marker across the backend, frontend, API documentation, OpenAPI metadata, security support table, dependency-lock header, release validator, and release notes.
- **DOC-002:** Replaced plain repository version labeling with aligned release, runtime, data-schema, CI, and CodeQL badges.
- **UI-001:** Added a compact visible version badge to the application header.

### Added

- **REL-003:** Added a guarded release-promotion workflow that waits for the required main-branch CI and CodeQL checks, then creates `v02.00.02` and publishes the versioned release notes when no matching release exists.
- Added regression checks for README, server-guide, and application-header badge alignment.

### Security

- The release workflow runs only after the permanent `Security and quality` workflow succeeds on `main`, or through an explicit manual dispatch.
- Release publication requires successful Python 3.10, Python 3.13, quality/security, and Python and JavaScript/TypeScript CodeQL checks for the exact release commit.
- The workflow uses pinned actions, exact version validation, least-privilege read permissions plus `contents: write`, and refuses a pre-existing tag that targets another commit.

### Compatibility

This is a non-breaking release metadata, documentation, and visible-label fix. API paths, authentication behavior, configuration fields, data schema 2, dependency versions, storage behavior, and bookmark data formats are unchanged from 02.00.01.

## [02.00.01] - 2026-08-13

### Fixed

- **PR #1 / CI-001:** Recovered the exact 02.00.00 application tree that passed tests, linting, typing, SAST, dependency auditing, CodeQL, configuration checks, performance checks, and the server smoke test. The prior publisher left only temporary payload files on `dev` after GitHub rejected a workflow-file push.
- **CI-002:** Replaced invalid or stale GitHub Action references with verified, immutable commits for `actions/checkout` v5, `actions/setup-python` v6, and `github/codeql-action` v4.
- **CI-003:** Changed the smoke test to derive its expected application version from `VERSION`, removing a release-specific workflow constant.
- **REL-001:** Removed temporary payload, unpacker, and publisher artifacts from the release tree.

### Added

- Added release-metadata regression tests covering version alignment, immutable workflow pins, migration-history preservation, and removal of the original bootstrap artifacts.
- Added release notes, rollback instructions, and copy-ready commit notes for the publication repair.

### Compatibility

This is a non-breaking publication and CI fix. API paths, authentication behavior, configuration fields, data schema 2, dependency versions, and bookmark data formats are unchanged from 02.00.00.

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
