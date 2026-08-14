.PHONY: install test lint typecheck security dependencies build performance validate

install:
	python -m pip install -r requirements-dev.txt

test:
	python -m pytest

lint:
	ruff check .

typecheck:
	mypy

security:
	bandit -r docs/server -ll -x docs/server/instance
	python scripts/scan_secrets.py

dependencies:
	python -m pip check
	pip-audit --no-deps -r docs/server/requirements.lock

build:
	python -m compileall -q docs/server tests scripts
	node --check docs/assets/app.js
	python scripts/validate_release.py

performance:
	python scripts/benchmark.py

validate: build lint typecheck security dependencies test performance
