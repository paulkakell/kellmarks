from __future__ import annotations

import sys
import tempfile
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

    # Measure the real locked preview/apply path, including validation and backup I/O.
    with tempfile.TemporaryDirectory(prefix="kellmarks-benchmark-") as directory:
        path = Path(directory)
        store = kellmarks.JsonStore(
            path / "data.json", path / "no-seed", path / "no-legacy",
            max_entries=10_000, max_data_bytes=16_777_216,
        )
        store.initialize()
        original = kellmarks.normalize_import_entries(entries[:10_000], 10_000)
        store.replace(original)
        incoming = kellmarks.normalize_import_entries(entries[:5_000], 5_000)
        for item in incoming:
            item["tags"].append("reviewed")
        options = {"mode": "merge", "title_source": "existing", "description_source": "existing"}
        started = time.perf_counter()
        preview = store.reviewed_import(incoming, **options)
        applied = store.reviewed_import(
            preview["incomingEntries"], **options, apply=True,
            base_revision=preview["baseRevision"],
        )
        elapsed = time.perf_counter() - started
        if applied["totalCount"] != 10_000 or applied["updated"] != 5_000 or elapsed >= 6.0:
            raise SystemExit(f"reviewed import performance failed: elapsed={elapsed:.3f}s")
        print(f"reviewed import passed: 10,000-entry library, 5,000 matches, preview+apply {elapsed:.3f}s")


if __name__ == "__main__":
    main()
