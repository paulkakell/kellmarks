from __future__ import annotations

import re
from pathlib import Path

import app as kellmarks

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")
ACTION_PATTERN = re.compile(r"uses:\s+[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_release_metadata_is_aligned() -> None:
    version = read("VERSION").strip()
    assert version == "02.00.02"
    assert VERSION_PATTERN.fullmatch(version)
    assert kellmarks.APP_VERSION == version
    assert f'const APP_VERSION = "{version}";' in read("docs/assets/app.js")
    assert f'version: "{version}"' in read("docs/openapi.yaml")
    assert f"## [{version}]" in read("CHANGELOG.md")
    assert f"# Kellmarks {version}" in read(f"docs/releases/{version}.md")


def test_version_badges_are_aligned() -> None:
    version = read("VERSION").strip()
    readme = read("README.md")
    server_readme = read("docs/server/README.md")
    index = read("docs/index.html")
    assert f"img.shields.io/badge/version-{version}-FFD700" in readme
    assert f"docs/releases/{version}.md" in readme
    assert f"img.shields.io/badge/version-{version}-FFD700" in server_readme
    assert f"../releases/{version}.md" in server_readme
    assert f'aria-label="Kellmarks version {version}"' in index
    assert f">v{version}<" in index


def test_permanent_workflows_use_immutable_action_references() -> None:
    for relative in (
        ".github/workflows/ci.yml",
        ".github/workflows/codeql.yml",
        ".github/workflows/release.yml",
    ):
        for line in read(relative).splitlines():
            if "uses:" in line:
                assert ACTION_PATTERN.search(line.strip()), line


def test_release_bootstrap_artifacts_are_absent() -> None:
    assert not (ROOT / ".release").exists()
    assert not (ROOT / ".github/workflows/apply-release.yml").exists()
    assert not (ROOT / ".github/workflows/publish-release-code.yml").exists()
    assert not (ROOT / ".github/workflows/release-repair.yml").exists()
    assert not (ROOT / ".github/workflows/release-version-badges.yml").exists()
    assert not (ROOT / "scripts/release_020001.py").exists()
    assert not (ROOT / "scripts/release_020002.py").exists()


def test_migration_backup_name_preserves_release_history() -> None:
    assert "data.pre-v02.00.00.json" in read("docs/server/app.py")
    assert "data.pre-v02.00.00.json" in read("docs/releases/02.00.01.md")
    assert "data.pre-v02.00.00.json" in read("docs/releases/02.00.02.md")
