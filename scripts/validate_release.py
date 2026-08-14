from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "02.00.01"
VERSION_PATTERN = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")


class StrictHTMLParser(HTMLParser):
    pass


def fail(message: str) -> None:
    print(f"release validation failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def read(relative: str) -> str:
    path = ROOT / relative
    if not path.is_file():
        fail(f"required file is missing: {relative}")
    return path.read_text(encoding="utf-8")


def main() -> None:
    version = read("VERSION").strip()
    if not VERSION_PATTERN.fullmatch(version):
        fail("VERSION must use xx.xx.xx format")
    if version != EXPECTED_VERSION:
        fail(f"expected VERSION {EXPECTED_VERSION}, found {version}")

    version_checks = {
        "docs/server/app.py": f'APP_VERSION = "{version}"',
        "docs/assets/app.js": f'const APP_VERSION = "{version}";',
        "docs/openapi.yaml": f'version: "{version}"',
        "CHANGELOG.md": f"## [{version}]",
        "docs/releases/02.00.01.md": f"# Kellmarks {version}",
    }
    for relative, marker in version_checks.items():
        if marker not in read(relative):
            fail(f"version marker is missing from {relative}")

    sample = json.loads(read("docs/assets/sample-data.json"))
    if sample.get("version") != 2 or not isinstance(sample.get("entries"), list):
        fail("sample data does not use schema version 2")
    if (ROOT / "docs" / "assets" / "data.json").exists():
        fail("runtime data must not exist in the public assets directory")

    app_source = read("docs/server/app.py")
    forbidden = [
        'Access-Control-Allow-Origin"] = "*"',
        'app.run(host="0.0.0.0"',
        "debug=True",
    ]
    for marker in forbidden:
        if marker in app_source:
            fail(f"unsafe server marker detected: {marker}")

    for line in read("docs/server/requirements.lock").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "==" not in stripped:
            fail(f"runtime dependency is not pinned: {stripped}")

    workflow_sources = [
        read(".github/workflows/ci.yml"),
        read(".github/workflows/codeql.yml"),
    ]
    action_reference = re.compile(r"uses:\s+[^@\s]+@([0-9a-f]{40})(?:\s+#.*)?$")
    for workflow in workflow_sources:
        for line in workflow.splitlines():
            if "uses:" not in line:
                continue
            if not action_reference.search(line.strip()):
                fail(f"GitHub Action is not pinned to a full commit SHA: {line.strip()}")

    environment_example = read(".env.example")
    if "KELLMARKS_REMOTE_ACCESS" in environment_example:
        fail("obsolete non-loopback development-server configuration remains")
    if re.search(r"^KELLMARKS_AUTH_TOKEN=.+$", environment_example, re.MULTILINE):
        fail(".env.example must not contain an authentication token")

    parser = StrictHTMLParser()
    parser.feed(read("docs/index.html"))
    parser.close()

    required_docs = [
        "README.md",
        "SECURITY.md",
        "CHANGELOG.md",
        "docs/API.md",
        "docs/openapi.yaml",
        "docs/SECURITY_ARCHITECTURE.md",
        "docs/server/README.md",
        "docs/releases/02.00.01.md",
    ]
    for relative in required_docs:
        read(relative)

    print(f"release validation passed for Kellmarks {version}")


if __name__ == "__main__":
    main()
