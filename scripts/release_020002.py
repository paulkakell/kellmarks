from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_VERSION = "02.00.01"
NEW_VERSION = "02.00.02"
RELEASE_DATE = "2026-08-13"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    content = read(relative)
    count = content.count(old)
    if count != 1:
        raise SystemExit(
            f"expected one marker in {relative}, found {count}: {old!r}"
        )
    write(relative, content.replace(old, new, 1))


def replace_all(relative: str, old: str, new: str) -> None:
    content = read(relative)
    if old not in content:
        raise SystemExit(f"marker is missing in {relative}: {old!r}")
    write(relative, content.replace(old, new))


def update_version_markers() -> None:
    current = read("VERSION").strip()
    if current != OLD_VERSION:
        raise SystemExit(f"expected VERSION {OLD_VERSION}, found {current}")

    write("VERSION", f"{NEW_VERSION}\n")
    replace_once(
        "docs/server/app.py",
        f'APP_VERSION = "{OLD_VERSION}"',
        f'APP_VERSION = "{NEW_VERSION}"',
    )
    replace_once(
        "docs/assets/app.js",
        f'const APP_VERSION = "{OLD_VERSION}";',
        f'const APP_VERSION = "{NEW_VERSION}";',
    )
    replace_all(
        "docs/openapi.yaml",
        f'"{OLD_VERSION}"',
        f'"{NEW_VERSION}"',
    )
    replace_all("docs/API.md", OLD_VERSION, NEW_VERSION)
    replace_once(
        "README.md",
        f"Version: **{OLD_VERSION}**",
        f"Version: **{NEW_VERSION}**",
    )
    replace_once(
        "docs/server/README.md",
        f"# Kellmarks server {OLD_VERSION}",
        f"# Kellmarks server {NEW_VERSION}",
    )
    replace_once(
        "SECURITY.md",
        f"| {OLD_VERSION} | Yes |",
        f"| {NEW_VERSION} | Yes |\n| {OLD_VERSION} | Yes |",
    )
    replace_once(
        "docs/SECURITY_ARCHITECTURE.md",
        f"Kellmarks {OLD_VERSION} is designed",
        f"Kellmarks {NEW_VERSION} is designed",
    )
    replace_once(
        "docs/server/requirements.lock",
        f"# Runtime dependency lock for Kellmarks {OLD_VERSION}.",
        f"# Runtime dependency lock for Kellmarks {NEW_VERSION}.",
    )
    replace_all("scripts/validate_release.py", OLD_VERSION, NEW_VERSION)


def add_markdown_badges() -> None:
    readme_badges = f"""[![Version {NEW_VERSION}](https://img.shields.io/badge/version-{NEW_VERSION}-FFD700?style=flat-square&labelColor=000000)](docs/releases/{NEW_VERSION}.md)
[![Latest release](https://img.shields.io/github/v/release/paulkakell/kellmarks?display_name=tag&sort=semver&style=flat-square&label=release)](https://github.com/paulkakell/kellmarks/releases/latest)
[![Python 3.10 and 3.13](https://img.shields.io/badge/python-3.10%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Data schema 2](https://img.shields.io/badge/data%20schema-2-FFD700?style=flat-square&labelColor=000000)](docs/API.md)
[![Security and quality](https://github.com/paulkakell/kellmarks/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/paulkakell/kellmarks/actions/workflows/ci.yml)
[![CodeQL](https://github.com/paulkakell/kellmarks/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/paulkakell/kellmarks/actions/workflows/codeql.yml)"""

    replace_once(
        "README.md",
        "# Kellmarks\n\nKellmarks is",
        f"# Kellmarks\n\n{readme_badges}\n\nKellmarks is",
    )

    server_badges = f"""[![Version {NEW_VERSION}](https://img.shields.io/badge/version-{NEW_VERSION}-FFD700?style=flat-square&labelColor=000000)](../releases/{NEW_VERSION}.md)
[![Python 3.10 and 3.13](https://img.shields.io/badge/python-3.10%20%7C%203.13-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Data schema 2](https://img.shields.io/badge/data%20schema-2-FFD700?style=flat-square&labelColor=000000)](../API.md)"""

    replace_once(
        "docs/server/README.md",
        f"# Kellmarks server {NEW_VERSION}\n\nThe Flask server",
        f"# Kellmarks server {NEW_VERSION}\n\n{server_badges}\n\nThe Flask server",
    )


def add_application_badge() -> None:
    replace_once(
        "docs/index.html",
        """            <h1>Kellmarks</h1>
            <div class="sub">Local first, protected, searchable</div>""",
        f"""            <div class="brand-title">
              <h1>Kellmarks</h1>
              <span class="version-badge" aria-label="Kellmarks version {NEW_VERSION}">v{NEW_VERSION}</span>
            </div>
            <div class="sub">Local first, protected, searchable</div>""",
    )

    replace_once(
        "docs/assets/app.css",
        ".brand h1{margin:0;font-size:16px;letter-spacing:.5px;font-weight:650;}\n",
        """.brand-title{display:flex;align-items:center;gap:8px;}
.brand h1{margin:0;font-size:16px;letter-spacing:.5px;font-weight:650;}
.version-badge{display:inline-flex;align-items:center;min-height:20px;padding:2px 7px;border:1px solid rgba(255,215,0,.5);border-radius:999px;background:rgba(255,215,0,.14);color:var(--accent);font-family:var(--mono);font-size:10px;font-weight:750;letter-spacing:.25px;white-space:nowrap;}
""",
    )


def update_release_validation() -> None:
    replace_once(
        "scripts/validate_release.py",
        """        "docs/assets/app.js": f'const APP_VERSION = "{version}";',
        "docs/openapi.yaml": f'version: "{version}"',""",
        """        "docs/assets/app.js": f'const APP_VERSION = "{version}";',
        "README.md": f"img.shields.io/badge/version-{version}-FFD700",
        "docs/server/README.md": f"img.shields.io/badge/version-{version}-FFD700",
        "docs/index.html": f'aria-label="Kellmarks version {version}"',
        "docs/openapi.yaml": f'version: "{version}"',""",
    )
    replace_once(
        "scripts/validate_release.py",
        """    workflow_sources = [
        read(".github/workflows/ci.yml"),
        read(".github/workflows/codeql.yml"),
    ]""",
        """    workflow_sources = [
        read(".github/workflows/ci.yml"),
        read(".github/workflows/codeql.yml"),
        read(".github/workflows/release.yml"),
    ]""",
    )
    replace_once(
        "scripts/validate_release.py",
        """    parser = StrictHTMLParser()
    parser.feed(read("docs/index.html"))
    parser.close()
""",
        """    release_workflow = read(".github/workflows/release.yml")
    if "pull_request_target:" in release_workflow:
        fail("release workflow must not run with pull_request_target")
    if "checks: read" not in release_workflow or "contents: write" not in release_workflow:
        fail("release workflow permissions are incomplete")

    parser = StrictHTMLParser()
    parser.feed(read("docs/index.html"))
    parser.close()
""",
    )


def update_changelog() -> None:
    changelog = read("CHANGELOG.md")
    marker = f"## [{OLD_VERSION}]"
    if marker not in changelog:
        raise SystemExit(f"{OLD_VERSION} changelog marker is missing")

    section = f"""## [{NEW_VERSION}] - {RELEASE_DATE}

### Fixed

- **REL-002:** Synchronized the current release marker across the backend, frontend, API documentation, OpenAPI metadata, security support table, dependency-lock header, release validator, and release notes.
- **DOC-002:** Replaced plain repository version labeling with aligned release, runtime, data-schema, CI, and CodeQL badges.
- **UI-001:** Added a compact visible version badge to the application header.

### Added

- **REL-003:** Added a guarded release-promotion workflow that waits for the required main-branch CI and CodeQL checks, then creates `v{NEW_VERSION}` and publishes the versioned release notes when no matching release exists.
- Added regression checks for README, server-guide, and application-header badge alignment.

### Security

- The release workflow runs only after the permanent `Security and quality` workflow succeeds on `main`, or through an explicit manual dispatch.
- Release publication requires successful Python 3.10, Python 3.13, quality/security, and Python and JavaScript/TypeScript CodeQL checks for the exact release commit.
- The workflow uses pinned actions, exact version validation, least-privilege read permissions plus `contents: write`, and refuses a pre-existing tag that targets another commit.

### Compatibility

This is a non-breaking release metadata, documentation, and visible-label fix. API paths, authentication behavior, configuration fields, data schema 2, dependency versions, storage behavior, and bookmark data formats are unchanged from {OLD_VERSION}.

"""
    write("CHANGELOG.md", changelog.replace(marker, section + marker, 1))


def write_release_notes() -> None:
    notes = f"""# Kellmarks {NEW_VERSION}

## Release classification

Bug-fix release with additive version badges and release automation. Non-breaking.

## Purpose

This release aligns every current-version badge and visible release marker before PR #1 is merged. Historical references to the 02.00.00 security migration and backup file remain unchanged.

## Changes

- Updated the traceable version from {OLD_VERSION} to {NEW_VERSION}.
- Added release, Python-runtime, data-schema, CI, and CodeQL badges to the primary README.
- Added release, Python-runtime, and data-schema badges to the server guide.
- Added a visible `v{NEW_VERSION}` badge to the application header.
- Aligned backend, frontend, API, OpenAPI, security policy, lock-file, validation, changelog, and release-note version markers.
- Added `.github/workflows/release.yml` to publish a matching tag and GitHub release after required main-branch checks succeed.
- Added badge-alignment regression coverage.

Issue references: PR #1, REL-002, REL-003, DOC-002, UI-001. Security controls SEC-001 through SEC-006 are retained unchanged.

## Automated validation

The release gate runs:

- unit, integration, regression, migration, configuration, concurrency, security, observability, store, API, release-metadata, and external-search tests;
- branch coverage with an 85 percent minimum;
- Python compilation and JavaScript syntax validation;
- Ruff and mypy;
- Bandit and the repository secret-pattern scanner;
- `pip check` and `pip-audit` against the pinned runtime lock;
- release and configuration validation;
- the 25,000-entry performance regression check;
- a live loopback server health smoke test;
- CodeQL for Python and JavaScript/TypeScript.

## Security review

Runtime authentication, authorization, exact-origin CORS, Trusted Host validation, request validation, private atomic storage, rate controls, structured logging, secret handling, and bounded external requests are unchanged.

The new release workflow:

- runs after the permanent main-branch security-and-quality workflow completes successfully;
- verifies the exact commit has successful Python 3.10, Python 3.13, quality/security, and Python and JavaScript/TypeScript CodeQL checks;
- validates the fixed-width version format and versioned release-note path;
- uses a pinned checkout action and the repository-scoped GitHub token;
- grants `actions: read`, `checks: read`, `contents: write`, and no broader permissions;
- is idempotent when the release already exists;
- refuses to publish from an existing tag that targets a different commit.

No secret values or new authentication surfaces are introduced.

## Dependency validation

Runtime and development dependency versions are unchanged from {OLD_VERSION}. Existing lock files remain authoritative and are revalidated with `pip check` and `pip-audit`.

## Build and configuration validation

The application installs in a fresh runner environment and compiles before tests. No environment variable, default, feature flag, API path, or configuration behavior changes. The data schema remains 2.

## Database and migration review

No database or JSON schema migration is required. The 02.00.00 legacy migration and `data.pre-v02.00.00.json` backup name remain unchanged intentionally.

## Performance, logging, and observability

Core search, storage, and I/O logic are unchanged. The standard 25,000-entry benchmark and live health smoke test are rerun. Structured request and security logs retain their existing fields and redaction behavior.

## Backward compatibility

{NEW_VERSION} is backward compatible with {OLD_VERSION}. Endpoint paths, request and response shapes, configuration names, schema-2 data, and import/export formats remain stable.

## Rollback plan

1. Stop the service and preserve the private data file, `.bak`, and `data.pre-v02.00.00.json` when present.
2. Restore commit `67b6a2177e514a947bab64716d887a4ab88547a2` or the {OLD_VERSION} deployment artifact.
3. Restore the pinned dependency environment.
4. Run `/api/health`, entry-count, import/export, and disposable CRUD checks before restoring traffic.
5. Delete `v{NEW_VERSION}` and its GitHub release only when the published artifact must be withdrawn; do not move an existing release tag.

## Release artifacts

- merge commit on `main`
- tag `v{NEW_VERSION}`
- GitHub release populated from this document
- `VERSION`
- `CHANGELOG.md`
- OpenAPI {NEW_VERSION}
- pinned runtime and development dependencies
- CI, security, CodeQL, performance, and smoke-test evidence

## Copy-ready commit notes

```text
fix(release): align Kellmarks {NEW_VERSION} version badges

- advance the traceable bug-fix version to {NEW_VERSION}
- add aligned release, Python, data-schema, CI, and CodeQL badges
- show v{NEW_VERSION} in the application header
- align backend, frontend, API, OpenAPI, security, lock, and validation markers
- add guarded post-CI tag and GitHub release publication
- add badge-alignment regression checks
- rerun tests, coverage, lint, typing, SAST, secret scan, dependency audit,
  release validation, performance validation, live smoke testing, and CodeQL

Classification: fix with additive UI, documentation, tests, and release automation
Breaking: no
Issues: PR #1, REL-002, REL-003, DOC-002, UI-001
Security inheritance: SEC-001, SEC-002, SEC-003, SEC-004, SEC-005, SEC-006
Version: {NEW_VERSION}
Tag: v{NEW_VERSION}
Rollback target: 67b6a2177e514a947bab64716d887a4ab88547a2
```
"""
    write(f"docs/releases/{NEW_VERSION}.md", notes)


def update_regression_tests() -> None:
    replace_once(
        "tests/test_release_metadata.py",
        f'    assert version == "{OLD_VERSION}"',
        f'    assert version == "{NEW_VERSION}"',
    )
    replace_once(
        "tests/test_release_metadata.py",
        """def test_permanent_workflows_use_immutable_action_references() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/codeql.yml"):""",
        """def test_permanent_workflows_use_immutable_action_references() -> None:
    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/release.yml",
    ):""",
    )
    marker = "\n\ndef test_permanent_workflows_use_immutable_action_references() -> None:"
    content = read("tests/test_release_metadata.py")
    if marker not in content:
        raise SystemExit("release metadata test insertion marker is missing")
    badge_test = f'''


def test_version_badges_are_aligned() -> None:
    version = read("VERSION").strip()
    readme = read("README.md")
    server_readme = read("docs/server/README.md")
    index = read("docs/index.html")
    assert f"img.shields.io/badge/version-{{version}}-FFD700" in readme
    assert f"docs/releases/{{version}}.md" in readme
    assert f"img.shields.io/badge/version-{{version}}-FFD700" in server_readme
    assert f"../releases/{{version}}.md" in server_readme
    assert f'aria-label="Kellmarks version {{version}}"' in index
    assert f">v{{version}}<" in index
'''
    write(
        "tests/test_release_metadata.py",
        content.replace(marker, badge_test + marker, 1),
    )


def main() -> None:
    update_version_markers()
    add_markdown_badges()
    add_application_badge()
    update_release_validation()
    update_changelog()
    write_release_notes()
    update_regression_tests()
    print(f"prepared Kellmarks {NEW_VERSION} version-badge release")


if __name__ == "__main__":
    main()
