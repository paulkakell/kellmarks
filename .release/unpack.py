from __future__ import annotations

import base64
import hashlib
import io
import os
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path.cwd().resolve()
RELEASE_DIR = ROOT / ".release"
MAX_ARCHIVE_BYTES = 5_000_000
MAX_FILE_BYTES = 2_000_000


def fail(message: str) -> None:
    raise SystemExit(f"release payload validation failed: {message}")


def safe_destination(member_name: str) -> Path:
    relative = PurePosixPath(member_name)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        fail(f"unsafe archive path: {member_name}")
    destination = ROOT.joinpath(*relative.parts).resolve()
    try:
        destination.relative_to(ROOT)
    except ValueError:
        fail(f"archive path escapes repository: {member_name}")
    return destination


def main() -> None:
    chunk_paths = sorted(RELEASE_DIR.glob("payload-*.part"))
    if not chunk_paths:
        fail("payload chunks are missing")
    encoded = "".join(path.read_text(encoding="ascii").strip() for path in chunk_paths)
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        fail(f"payload is not valid base64: {exc}")
    if len(payload) > MAX_ARCHIVE_BYTES:
        fail("payload archive exceeds the bootstrap limit")

    expected = (RELEASE_DIR / "payload.sha256").read_text(encoding="ascii").strip()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        fail(f"payload checksum mismatch: expected {expected}, found {actual}")

    total_size = 0
    extracted = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile():
                    fail(f"payload contains a non-regular file: {member.name}")
                if member.size < 0 or member.size > MAX_FILE_BYTES:
                    fail(f"payload file exceeds the per-file limit: {member.name}")
                total_size += member.size
                if total_size > MAX_ARCHIVE_BYTES:
                    fail("expanded payload exceeds the bootstrap limit")
                source = archive.extractfile(member)
                if source is None:
                    fail(f"payload file could not be read: {member.name}")
                content = source.read(MAX_FILE_BYTES + 1)
                if len(content) != member.size:
                    fail(f"payload file size mismatch: {member.name}")
                destination = safe_destination(member.name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                os.chmod(destination, 0o644)
                extracted += 1
    except (OSError, tarfile.TarError) as exc:
        fail(f"payload archive could not be extracted: {exc}")

    legacy_public_data = ROOT / "docs" / "assets" / "data.json"
    legacy_public_data.unlink(missing_ok=True)
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if version != "02.00.00":
        fail(f"unexpected payload version: {version}")
    print(f"validated and extracted {extracted} release files for Kellmarks {version}")


if __name__ == "__main__":
    main()
