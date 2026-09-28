"""Prevent cross-platform emulation bootstrap from inheriting the target platform."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_platform_override_is_scoped_after_emulator_bootstrap():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker.yml").read_text())
    job = workflow["jobs"]["docker"]
    assert "DOCKER_DEFAULT_PLATFORM" not in job.get("env", {})
    steps = job["steps"]
    setup = next(step for step in steps if "docker/setup-qemu-action@" in step.get("uses", ""))
    assert "DOCKER_DEFAULT_PLATFORM" not in setup.get("env", {})
    assert setup["with"]["cache-image"] is False
    targets = [step for step in steps if "DOCKER_DEFAULT_PLATFORM" in step.get("env", {})]
    assert len(targets) == 3
    for step in targets:
        assert steps.index(step) > steps.index(setup)
        assert step["env"]["DOCKER_DEFAULT_PLATFORM"] == "${{ matrix.platform }}"
