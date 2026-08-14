from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd().resolve()


def replace_count(relative: str, old: str, new: str, expected: int = 1) -> None:
    path = ROOT / relative
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != expected:
        raise SystemExit(
            f"release follow-up pattern count in {relative}: "
            f"expected {expected}, found {count}"
        )
    path.write_text(content.replace(old, new), encoding="utf-8")


def main() -> None:
    replace_count(
        "docs/server/app.py",
        "import hmac\nimport ipaddress\n",
        "import hmac\nimport importlib\nimport ipaddress\n",
    )
    replace_count(
        "docs/server/app.py",
        "from typing import Any, TypeVar\n",
        "from typing import Any, TypeVar, cast\n",
    )
    replace_count(
        "docs/server/app.py",
        '            if os.name == "nt":\n'
        "                import msvcrt\n\n"
        "                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)\n"
        "                try:\n"
        "                    yield\n"
        "                finally:\n"
        "                    handle.seek(0)\n"
        "                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)\n",
        '            if os.name == "nt":\n'
        '                msvcrt = cast(Any, importlib.import_module("msvcrt"))\n'
        "                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)\n"
        "                try:\n"
        "                    yield\n"
        "                finally:\n"
        "                    handle.seek(0)\n"
        "                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)\n",
    )
    replace_count(
        "docs/server/app.py",
        '        def mutation(data: dict[str, Any]) -> dict[str, Any]:\n'
        '            for index, current in enumerate(data["entries"]):\n'
        '                if current["id"] == normalized_id:\n'
        '                    return data["entries"].pop(index)\n'
        "            raise LookupError\n",
        '        def mutation(data: dict[str, Any]) -> dict[str, Any]:\n'
        '            entries = cast(list[dict[str, Any]], data["entries"])\n'
        "            for index, current in enumerate(entries):\n"
        '                if current["id"] == normalized_id:\n'
        "                    return entries.pop(index)\n"
        "            raise LookupError\n",
    )
    replace_count(
        ".github/workflows/ci.yml",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4",
        "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5",
        2,
    )
    replace_count(
        ".github/workflows/ci.yml",
        "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5",
        "actions/setup-python@e797f83bcb11b83ae66e0230d6156d7c80228e7c # v6",
        2,
    )
    replace_count(
        ".github/workflows/codeql.yml",
        "actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4",
        "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5",
    )
    for action in ("init", "autobuild", "analyze"):
        replace_count(
            ".github/workflows/codeql.yml",
            f"github/codeql-action/{action}@"
            "f3712979fa5f215279b101dd0a2e3bdfb4353324 # v3",
            f"github/codeql-action/{action}@"
            "cc290b166002839ef66cbe0740fabefad66fca5b # v4",
        )
    print("applied mypy fixes and current GitHub Actions pins")


if __name__ == "__main__":
    main()
