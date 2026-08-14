from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "docs" / "server"))

import app as kellmarks  # noqa: E402


def main() -> None:
    entries = [
        {
            "title": f"Cloud security reference {index}",
            "url": f"https://example.com/{index}",
            "description": "identity vpn zero trust",
            "tags": ["work/security", "cloud/aws"],
        }
        for index in range(25_000)
    ]
    started = time.perf_counter()
    count = sum(
        1
        for entry in entries
        if kellmarks.matches_query(entry, 'vpn AND (aws OR azure) NOT personal')
    )
    elapsed = time.perf_counter() - started
    if count != len(entries) or elapsed >= 6.0:
        raise SystemExit(
            f"performance check failed: count={count}, elapsed={elapsed:.3f}s"
        )
    print(f"performance check passed: {count} entries in {elapsed:.3f}s")


if __name__ == "__main__":
    main()
