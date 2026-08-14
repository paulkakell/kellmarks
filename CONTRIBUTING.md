# Contributing

Changes should target the `dev` branch and use the repository release checklist.

## Required checks

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
make validate
```

A change that modifies behavior must add or update tests and documentation. Security-sensitive changes must review authentication, authorization, input validation, logs, dependencies, secrets, configuration, persistence, rollback, and compatibility.

Version numbers use fixed-width `Release.Feature.BugFix` form, such as `02.00.01`. Update `VERSION`, application constants, OpenAPI, changelog, and release notes together.

Do not commit runtime data, backup files, lock files, tokens, local environment files, coverage output, or virtual environments.
