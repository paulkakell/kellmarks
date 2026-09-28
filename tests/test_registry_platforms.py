"""Exercise registry round-trips on classic single-platform Docker image stores."""
from __future__ import annotations

import json
import runpy
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
RELEASE = runpy.run_path(str(ROOT / "scripts/publish_container.py"))
IMAGE = "ghcr.io/paulkakell/kellmarks"
INDEX = "sha256:" + "a" * 64
CHILDREN = ["sha256:" + "b" * 64, "sha256:" + "c" * 64]


def manifest():
    return {"manifests": [
        {"platform": {"os": "linux", "architecture": "amd64"}, "digest": CHILDREN[0]},
        {"platform": {"os": "linux", "architecture": "arm64"}, "digest": CHILDREN[1]},
        {"platform": {"os": "unknown", "architecture": "unknown"}, "digest": INDEX},
    ]}


def test_resolve_children_from_index_without_using_attestations():
    assert RELEASE["platform_references"](IMAGE, manifest()) == [
        ("linux/amd64", IMAGE + "@" + CHILDREN[0]),
        ("linux/arm64", IMAGE + "@" + CHILDREN[1]),
    ]


def test_ambiguous_platform_child_is_rejected():
    index = manifest()
    index["manifests"].append(index["manifests"][0])
    with pytest.raises(ValueError, match="unambiguous"):
        RELEASE["platform_references"](IMAGE, index)


@pytest.mark.parametrize("digest", ["", "latest", "sha256:invalid"])
def test_invalid_child_digest_is_rejected(digest):
    index = manifest()
    index["manifests"][1]["digest"] = digest
    with pytest.raises(ValueError, match="invalid image digest"):
        RELEASE["platform_references"](IMAGE, index)


def test_full_publisher_pulls_and_smokes_distinct_immutable_children(monkeypatch, tmp_path):
    function = RELEASE["main"]
    (tmp_path / "VERSION").write_text((ROOT / "VERSION").read_text())
    monkeypatch.setitem(function.__globals__, "ROOT", tmp_path)
    for key, value in {"RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(tmp_path / "output"),
                       "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
                       "GITHUB_REPOSITORY": "paulkakell/kellmarks",
                       "RELEASE_SHA": "d" * 40}.items():
        monkeypatch.setenv(key, value)
    calls = []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["docker", "buildx", "build"]:
            (tmp_path / "container-build.json").write_text(
                json.dumps({"containerimage.digest": INDEX}))
        output = json.dumps(manifest()) if args[-1] == "--raw" else ""
        return subprocess.CompletedProcess(args, 0, output, "")

    monkeypatch.setitem(function.__globals__, "run", runner)
    monkeypatch.setitem(function.__globals__, "inspect_existing",
                        Mock(side_effect=[None, None, INDEX]))
    assets = Mock()
    monkeypatch.setitem(function.__globals__, "write_assets", assets)
    function()
    pulls = [args for args, _ in calls if args[:2] == ["docker", "pull"]]
    assert pulls == [["docker", "pull", "--platform", platform, IMAGE + "@" + child]
                     for platform, child in zip(RELEASE["PLATFORMS"], CHILDREN, strict=True)]
    smoke = [kw["env"]["KELLMARKS_TEST_IMAGE"] for args, kw in calls
             if args[-1] == "scripts/docker_smoke.py"]
    assert smoke == [IMAGE + "@" + child for child in CHILDREN]
    assert all(INDEX not in args[-1] for args in pulls)
    assert assets.call_args.kwargs["digest"] == INDEX
    assert IMAGE + "@" + INDEX in (tmp_path / "summary").read_text()
