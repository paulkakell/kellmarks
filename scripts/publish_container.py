"""Publish a tested, versioned GHCR image and prepare public installation assets.

Run only in the release workflow after exact-commit checks and registry login.
No operator secrets or bookmark data are included in the build or release bundle.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = ("linux/amd64", "linux/arm64")
VERSION_RE = re.compile(r"[0-9]{2}\.[0-9]{2}\.[0-9]{2}")
SHA_RE = re.compile(r"[0-9a-f]{40}")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def validate_identity(version: str, revision: str, repository: str) -> str:
    if not VERSION_RE.fullmatch(version) or not SHA_RE.fullmatch(revision):
        raise ValueError("a release version and full commit SHA are required")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*/[a-z0-9][a-z0-9_.-]*", repository):
        raise ValueError("invalid lowercase GitHub repository")
    return f"ghcr.io/{repository}"


def checked_digest(value: str) -> str:
    if not DIGEST_RE.fullmatch(value):
        raise ValueError("invalid image digest")
    return value


def run(args: list[str], *, check: bool = True,
        env: dict[str, str] | None = None, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, env=env, check=False, capture_output=True,
                            text=True, timeout=timeout)
    if check and result.returncode:
        diagnostic = (result.stdout + result.stderr)[-12000:]
        for name in ("GH_TOKEN", "GITHUB_TOKEN"):
            secret = os.environ.get(name, "")
            if secret:
                diagnostic = diagnostic.replace(secret, "[REDACTED]")
        print(diagnostic, file=sys.stderr)
        result.check_returncode()
    return result


def inspect_existing(image: str, tag: str, version: str, revision: str) -> str | None:
    """Only an explicit missing manifest permits building; auth/network errors fail."""
    reference = f"{image}:{tag}"
    result = run(["docker", "buildx", "imagetools", "inspect", reference], check=False)
    if result.returncode:
        error = result.stderr.lower()
        if ("not found" in error or "manifest unknown" in error) and not any(
            text in error for text in ("denied", "unauthorized", "forbidden")
        ):
            return None
        raise RuntimeError("registry inspection failed; check package access and connectivity")
    run(["docker", "pull", "--platform", "linux/amd64", reference], timeout=300)
    info = json.loads(run(["docker", "image", "inspect", reference]).stdout)[0]
    labels = info["Config"].get("Labels") or {}
    if labels.get("org.opencontainers.image.version") != version or labels.get(
        "org.opencontainers.image.revision"
    ) != revision:
        raise RuntimeError("existing image belongs to another release; refusing to overwrite it")
    for value in info.get("RepoDigests", []):
        if value.startswith(image + "@"):
            return checked_digest(value.split("@", 1)[1])
    raise RuntimeError("registry image has no verified repository digest")


def validate_platforms(manifest: dict[str, Any]) -> None:
    platforms = {
        f"{item.get('platform', {}).get('os')}/{item.get('platform', {}).get('architecture')}"
        for item in manifest.get("manifests", [])
    }
    if not set(PLATFORMS).issubset(platforms):
        raise ValueError("image index must include Linux AMD64 and ARM64")


def write_assets(root: Path, destination: Path, *, image: str, version: str,
                 revision: str, digest: str, anonymous_pull: bool) -> None:
    checked_digest(digest)
    destination.mkdir(parents=True, exist_ok=True)
    # Explicit allowlist: never archive the working tree, .env, or a data volume.
    sources = {
        "docker-compose.yml": "docker-compose.yml",
        ".env.docker.example": ".env.docker.example",
        "compose.https.yaml": "compose.https.yaml",
        "docker/Caddyfile": "docker/Caddyfile",
        "docs/GHCR_INSTALLATION.md": "docs/GHCR_INSTALLATION.md",
        "docs/INSTALLATION.md": "docs/INSTALLATION.md",
    }
    record = {
        "version": version, "revision": revision, "image": image,
        "digest": digest, "reference": f"{image}@{digest}",
        "platforms": list(PLATFORMS), "anonymousPullAvailable": anonymous_pull,
    }
    metadata = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    files = {name: (root / source).read_bytes() for name, source in sources.items()}
    files["container.json"] = metadata
    bundle = io.BytesIO()
    with gzip.GzipFile(fileobj=bundle, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
    (destination / f"kellmarks-{version}-docker.tar.gz").write_bytes(bundle.getvalue())
    # Flat assets support a minimal two-file installation; the tar preserves paths.
    for name, content in files.items():
        (destination / Path(name).name).write_bytes(content)
    sums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(destination.iterdir()) if path.is_file() and path.name != "SHA256SUMS"
    )
    (destination / "SHA256SUMS").write_text(sums, encoding="utf-8")


def main() -> None:
    version = (ROOT / "VERSION").read_text().strip()
    revision = os.environ["RELEASE_SHA"]
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    image = validate_identity(version, revision, repository)
    destination = Path(os.environ["RUNNER_TEMP"]) / "kellmarks-release"
    metadata_path = Path(os.environ["RUNNER_TEMP"]) / "container-build.json"
    existing_version = inspect_existing(image, version, version, revision)
    digest = existing_version or inspect_existing(image, f"sha-{revision}", version, revision)
    if digest is None:
        run([
            "docker", "buildx", "build", "--pull", "--platform", ",".join(PLATFORMS),
            "--build-arg", f"KELLMARKS_VERSION={version}",
            "--build-arg", f"VCS_REF={revision}", "--provenance=mode=max", "--sbom=true",
            "--metadata-file", str(metadata_path), "--tag", f"{image}:sha-{revision}",
            "--push", ".",
        ], timeout=1800)
        digest = checked_digest(json.loads(metadata_path.read_text())["containerimage.digest"])
    reference = f"{image}@{digest}"
    manifest = json.loads(run(["docker", "buildx", "imagetools", "inspect", reference,
                               "--raw"]).stdout)
    validate_platforms(manifest)
    for platform in PLATFORMS:
        run(["docker", "pull", "--platform", platform, reference], timeout=300)
        environment = dict(os.environ, KELLMARKS_TEST_IMAGE=reference,
                           KELLMARKS_TEST_COMPOSE="docker-compose.yml",
                           DOCKER_DEFAULT_PLATFORM=platform)
        run([sys.executable, "scripts/docker_smoke.py"], env=environment, timeout=900)
        print(f"Published digest passed full Compose smoke test on {platform}", flush=True)
    # Version tags are promoted only after testing the actual registry digest.
    if existing_version is None:
        run(["docker", "buildx", "imagetools", "create", "--tag", f"{image}:{version}",
             reference], timeout=300)
    if inspect_existing(image, version, version, revision) != digest:
        raise RuntimeError("promoted version does not match the tested digest")
    # Inspect anonymously without exposing the workflow's credential store.
    anonymous_config = Path(os.environ["RUNNER_TEMP"]) / "anonymous-docker"
    anonymous_config.mkdir(exist_ok=True)
    probe = run(["docker", "--config", str(anonymous_config), "manifest", "inspect",
                 f"{image}:{version}"], check=False)
    anonymous_pull = probe.returncode == 0
    if not anonymous_pull:
        print("::warning::Anonymous GHCR pull was not verified. Check package visibility; "
              "a new GHCR package is private until its owner makes it public.")
    write_assets(ROOT, destination, image=image, version=version, revision=revision,
                 digest=digest, anonymous_pull=anonymous_pull)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        output.write(f"image={image}\ndigest={digest}\nassets={destination}\n")
    with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
        summary.write(f"## Container {version}\n\n`{reference}`\n\n"
                      f"Commit: `{revision}`. Platforms: {', '.join(PLATFORMS)}.\n\n"
                      f"Anonymous manifest access verified: **{anonymous_pull}**.\n")


if __name__ == "__main__":
    main()
