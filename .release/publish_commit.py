from __future__ import annotations

import base64
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_VERSION = "2022-11-28"
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def git_output(*args: str) -> bytes:
    return subprocess.check_output(["git", *args])


def api_request(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    repository = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    url = f"https://api.github.com/repos/{repository}{path}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "kellmarks-release-publisher",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"GitHub API {exc.code} for {path}: {detail}") from exc
    if not isinstance(result, dict):
        raise SystemExit(f"GitHub API returned an invalid object for {path}")
    return result


def create_complete_tree() -> str:
    raw_entries = git_output("ls-tree", "-r", "-z", "--full-tree", "HEAD")
    tree_entries: list[dict[str, str]] = []
    for raw_entry in raw_entries.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode, object_type, _local_sha = metadata.decode("ascii").split()
        if object_type != "blob":
            raise SystemExit(f"unsupported Git object type: {object_type}")
        relative_path = raw_path.decode("utf-8")
        content = Path(relative_path).read_bytes()
        blob = api_request(
            "/git/blobs",
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        blob_sha = blob.get("sha")
        if not isinstance(blob_sha, str):
            raise SystemExit(f"GitHub did not return a blob SHA for {relative_path}")
        tree_entries.append(
            {
                "path": relative_path,
                "mode": mode,
                "type": "blob",
                "sha": blob_sha,
            }
        )

    tree = api_request("/git/trees", {"tree": tree_entries})
    tree_sha = tree.get("sha")
    if not isinstance(tree_sha, str):
        raise SystemExit("GitHub did not return a tree SHA")
    return tree_sha


def create_release_commit(tree_sha: str) -> str:
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = {"name": BOT_NAME, "email": BOT_EMAIL, "date": now}
    message = git_output("log", "-1", "--format=%B", "HEAD").decode("utf-8").rstrip()
    commit = api_request(
        "/git/commits",
        {
            "message": message,
            "tree": tree_sha,
            "parents": [os.environ["GITHUB_SHA"]],
            "author": identity,
            "committer": identity,
        },
    )
    commit_sha = commit.get("sha")
    if not isinstance(commit_sha, str):
        raise SystemExit("GitHub did not return a commit SHA")
    return commit_sha


def main() -> None:
    tree_sha = create_complete_tree()
    commit_sha = create_release_commit(tree_sha)
    print(f"VALIDATED_RELEASE_TREE={tree_sha}")
    print(f"VALIDATED_RELEASE_COMMIT={commit_sha}")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"tree_sha={tree_sha}\n")
            output.write(f"commit_sha={commit_sha}\n")


if __name__ == "__main__":
    main()
