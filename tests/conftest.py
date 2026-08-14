from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "docs" / "server"
sys.path.insert(0, str(SERVER_DIR))

IMPORT_DATA_PATH = Path(os.getenv("RUNNER_TEMP", "/tmp")) / (
    f"kellmarks-import-{os.getpid()}.json"
)
os.environ.setdefault("KELLMARKS_DATA_FILE", str(IMPORT_DATA_PATH))
os.environ.setdefault("KELLMARKS_TRUSTED_HOSTS", "localhost,127.0.0.1,[::1]")

import app as kellmarks  # noqa: E402


@pytest.fixture
def app(tmp_path: Path) -> Iterator[Flask]:
    application = kellmarks.create_app(
        {
            "TESTING": True,
            "DATA_PATH": tmp_path / "data.json",
            "SEED_PATH": tmp_path / "missing-sample.json",
            "LEGACY_DATA_PATH": tmp_path / "missing-legacy.json",
            "TRUSTED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
            "AUTH_TOKEN": "",
            "REQUIRE_AUTH": False,
            "ALLOWED_ORIGINS": frozenset(),
            "MAX_CONTENT_LENGTH": 1_048_576,
            "MAX_DATA_BYTES": 16_777_216,
            "MAX_ENTRIES": 10_000,
            "MAX_IMPORT_ENTRIES": 5_000,
            "WRITE_RATE_LIMIT": 10_000,
            "DDG_RATE_LIMIT": 10_000,
            "AUTH_RATE_LIMIT": 10_000,
        }
    )
    yield application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def make_app(tmp_path: Path):
    counter = 0

    def factory(**overrides: Any) -> Flask:
        nonlocal counter
        counter += 1
        directory = tmp_path / f"app-{counter}"
        directory.mkdir()
        config: dict[str, Any] = {
            "TESTING": True,
            "DATA_PATH": directory / "data.json",
            "SEED_PATH": directory / "missing-sample.json",
            "LEGACY_DATA_PATH": directory / "missing-legacy.json",
            "TRUSTED_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
            "AUTH_TOKEN": "",
            "REQUIRE_AUTH": False,
            "ALLOWED_ORIGINS": frozenset(),
            "MAX_CONTENT_LENGTH": 1_048_576,
            "MAX_DATA_BYTES": 16_777_216,
            "MAX_ENTRIES": 10_000,
            "MAX_IMPORT_ENTRIES": 5_000,
            "WRITE_RATE_LIMIT": 10_000,
            "DDG_RATE_LIMIT": 10_000,
            "AUTH_RATE_LIMIT": 10_000,
        }
        config.update(overrides)
        return kellmarks.create_app(config)

    return factory
