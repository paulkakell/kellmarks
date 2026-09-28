"""Compare downloaded release assets with exact prepared public inputs."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def verify_assets(expected: Path, downloaded: Path) -> int:
    source = {path.name: path for path in expected.iterdir()}
    actual = {path.name: path for path in downloaded.iterdir()}
    if not source or source.keys() != actual.keys():
        raise ValueError("release asset filenames differ from prepared inputs")
    for name in sorted(source):
        left, right = source[name], actual[name]
        if any(path.is_symlink() or not path.is_file() for path in (left, right)):
            raise ValueError("release assets must be regular files")
        if (left.stat().st_size != right.stat().st_size
                or hashlib.sha256(left.read_bytes()).digest()
                != hashlib.sha256(right.read_bytes()).digest()):
            raise ValueError(f"release asset content mismatch: {name}")
    return len(source)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", type=Path)
    parser.add_argument("downloaded", type=Path)
    args = parser.parse_args()
    count = verify_assets(args.expected, args.downloaded)
    print(f"Verified {count} downloaded release assets: names, sizes and SHA-256 hashes")


if __name__ == "__main__":
    main()
