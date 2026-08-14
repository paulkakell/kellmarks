from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_VERSION = "02.00.00"
NEW_VERSION = "02.00.01"
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
            f"expected one release marker in {relative}, found {count}: {old!r}"
        )
    write(relative, content.replace(old, new, 1))


def replace_all(relative: str, old: str, new: str) -> None:
    content = read(relative)
    if old not in content:
        raise SystemExit(f"release marker is missing in {relative}: {old!r}")
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


def update_changelog() -> None:
    changelog = read("CHANGELOG.md")
    marker = f"## [{OLD_VERSION}]"
    if marker not in changelog:
        raise SystemExit(f"{OLD_VERSION} changelog marker is missing")

    section = f"""## [{NEW_VERSION}] - {RELEASE_DATE}

### Fixed

- **PR #1 / CI-001:** Recovered the exact {OLD_VERSION} application tree that passed tests, linting, typing, SAST, dependency auditing, CodeQL, configuration checks, performance checks, and the server smoke test. The prior publisher left only temporary payload files on `dev` after GitHub rejected a workflow-file push.
- **CI-002:** Replaced invalid or stale GitHub Action references with verified, immutable commits for `actions/checkout` v5, `actions/setup-python` v6, and `github/codeql-action` v4.
- **CI-003:** Changed the smoke test to derive its expected application version from `VERSION`, removing a release-specific workflow constant.
- **REL-001:** Removed temporary payload, unpacker, and publisher artifacts from the release tree.

### Added

- Added release-metadata regression tests covering version alignment, immutable workflow pins, migration-history preservation, and removal of the original bootstrap artifacts.
- Added release notes, rollback instructions, and copy-ready commit notes for the publication repair.

### Compatibility

This is a non-breaking publication and CI fix. API paths, authentication behavior, configuration fields, data schema 2, dependency versions, and bookmark data formats are unchanged from {OLD_VERSION}.

"""
    write("CHANGELOG.md", changelog.replace(marker, section + marker, 1))


def write_release_notes() -> None:
    notes = f"""# Kellmarks {NEW_VERSION}

## Release classification

Bug-fix release. Non-breaking.

## Why this release exists

PR #1 failed because the `dev` branch contained a temporary release publisher rather than the application tree that had already passed the complete {OLD_VERSION} validation gate. CI could not find its dependency and project files, while CodeQL referenced an invalid action commit.

This release restores the validated application tree and makes the publication process traceable without changing runtime behavior.

## Changes

- Recovered validated source commit `4a4f42da1d0013bd3b134ea29e44addb262f1dda` and made it reachable from `dev`.
- Replaced temporary `.release` payloads and publisher workflows with the permanent application tree.
- Pinned `actions/checkout` v5 to `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09`.
- Pinned `actions/setup-python` v6 to `ece7cb06caefa5fff74198d8649806c4678c61a1`.
- Pinned `github/codeql-action` v4 to `ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd`.
- Made CI smoke validation read the expected version from `VERSION`.
- Added regression coverage for release metadata and bootstrap-file removal.

Issue references: PR #1, CI-001, CI-002, CI-003, REL-001. Security controls from SEC-001 through SEC-006 are retained unchanged.

## Automated validation

The publication gate runs:

- unit, integration, regression, migration, configuration, concurrency, security, observability, store, API, and external-search tests;
- branch coverage with an 85 percent minimum;
- Python compilation and JavaScript syntax validation;
- Ruff and mypy;
- Bandit and the repository secret-pattern scanner;
- `pip check` and `pip-audit` against the pinned runtime lock;
- release and configuration validation;
- the 25,000-entry performance regression check;
- a live loopback server health smoke test.

Permanent CI and CodeQL run again after the temporary repair workflow is removed.

## Security review

Authentication, authorization, exact-origin CORS, Trusted Host handling, request validation, private atomic storage, rate controls, structured logging, secret handling, and bounded external requests are unchanged from {OLD_VERSION}. No secrets are added. The repaired workflows use least-privilege permissions and immutable action references.

## Dependency validation

Runtime and development dependency versions are unchanged. The existing lock files are rebuilt only when dependencies change. This release revalidates the current files with `pip check` and `pip-audit`.

## Build and configuration validation

The application is installed in a fresh runner environment and compiled before tests. No environment variable, default, feature flag, or API configuration changes are introduced. The version marker advances to {NEW_VERSION}. The data schema remains 2.

## Database and migration review

No database or JSON schema migration is required. The {OLD_VERSION} legacy migration path and `data.pre-v02.00.00.json` backup name remain unchanged intentionally.

## Performance, logging, and observability

Core search, storage, and I/O logic are unchanged. The standard benchmark and live smoke test are rerun. Structured request and security logs retain their existing fields and redaction behavior.

## Backward compatibility

This release is backward compatible with {OLD_VERSION}. Endpoint paths, request and response shapes, configuration names, and schema-2 data remain stable.

## Rollback plan

1. Stop the service and preserve the private data file, `.bak`, and `data.pre-v02.00.00.json` when present.
2. Restore validated commit `4a4f42da1d0013bd3b134ea29e44addb262f1dda` or the {OLD_VERSION} deployment artifact.
3. Restore the pinned dependency environment.
4. Run `/api/health`, entry-count, import/export, and disposable CRUD checks before restoring traffic.
5. Do not roll back to the temporary publisher commits because they do not contain a deployable application tree.

## Promotion

Proposed tag after PR approval: `v{NEW_VERSION}`.

## Copy-ready commit notes

```text
fix(release): publish Kellmarks {NEW_VERSION}

- recover the validated {OLD_VERSION} application tree
- remove temporary release payload and publisher artifacts
- repair CI dependency paths by restoring the complete project tree
- pin checkout v5, setup-python v6, and CodeQL v4 to verified commits
- derive smoke-test version expectations from VERSION
- add release-metadata regression tests
- rerun tests, coverage, lint, typing, SAST, secret scan, dependency audit,
  release validation, performance validation, and live server smoke testing

Classification: fix, additive tests and documentation, non-breaking
Issues: PR #1, CI-001, CI-002, CI-003, REL-001
Security inheritance: SEC-001, SEC-002, SEC-003, SEC-004, SEC-005, SEC-006
Version: {NEW_VERSION}
Tag on promotion: v{NEW_VERSION}
Rollback target: 4a4f42da1d0013bd3b134ea29e44addb262f1dda
```
"""
    write(f"docs/releases/{NEW_VERSION}.md", notes)


def write_regression_tests() -> None:
    tests = f'''from __future__ import annotations

import re
from pathlib import Path

import app as kellmarks

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^\\d{{2}}\\.\\d{{2}}\\.\\d{{2}}$")
ACTION_PATTERN = re.compile(r"uses:\\s+[^@\\s]+@([0-9a-f]{{40}})(?:\\s+#.*)?$")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_metadata_is_aligned() -> None:
    version = read("VERSION").strip()
    assert version == "{NEW_VERSION}"
    assert VERSION_PATTERN.fullmatch(version)
    assert kellmarks.APP_VERSION == version
    assert f'const APP_VERSION = "{{version}}";' in read("docs/assets/app.js")
    assert f'version: "{{version}}"' in read("docs/openapi.yaml")
    assert f"## [{{version}}]" in read("CHANGELOG.md")
    assert f"# Kellmarks {{version}}" in read(f"docs/releases/{{version}}.md")


def test_permanent_workflows_use_immutable_action_references() -> None:
    for relative in (".github/workflows/ci.yml", ".github/workflows/codeql.yml"):
        for line in read(relative).splitlines():
            if "uses:" in line:
                assert ACTION_PATTERN.search(line.strip()), line


def test_original_bootstrap_artifacts_are_absent() -> None:
    assert not (ROOT / ".release").exists()
    assert not (ROOT / ".github/workflows/apply-release.yml").exists()
    assert not (ROOT / ".github/workflows/publish-release-code.yml").exists()


def test_migration_backup_name_preserves_release_history() -> None:
    assert "data.pre-v02.00.00.json" in read("docs/server/app.py")
    assert "data.pre-v02.00.00.json" in read("docs/releases/{NEW_VERSION}.md")
'''
    write("tests/test_release_metadata.py", tests)


def main() -> None:
    update_version_markers()
    update_changelog()
    write_release_notes()
    write_regression_tests()
    print(f"prepared Kellmarks {NEW_VERSION} publication repair")


if __name__ == "__main__":
    main()
