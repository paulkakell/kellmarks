# Contributing

Changes should target the `dev` branch and use the repository release checklist.

## Issues, discussions, and sponsorship

Use the [issue forms](https://github.com/paulkakell/kellmarks/issues/new/choose) for bugs, concrete feature requests, and documentation improvements. Use [Discussions](https://github.com/paulkakell/kellmarks/discussions) for questions, early ideas, and sharing workflows. Follow [SECURITY.md](SECURITY.md) rather than posting vulnerabilities publicly. Never include private bookmarks or tokens in reports.

See the [community guide](.github/COMMUNITY.md) for discussion categories, participation guidance, and sponsorship setup and verification.

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

## Branch integration and cleanup

Keep main for releases and dev for contributions and dependency updates. Consolidate related updates on a versioned release branch, require all tests and security checks, then merge to main and fast-forward dev. Never infer that a long-lived branch is obsolete solely from age or commit containment.

CodeQL init, autobuild, and analyze must share one full commit SHA. Dependabot groups github/codeql-action/* to keep these updates together. Run `python scripts/validate_release.py` to reject mixed versions before opening a release PR.

After a release, remove only short-lived branches whose recorded tips are unchanged, unprotected, and ancestors of both main and dev, with no open dependent pull requests. Preserve a source-commit ledger in release notes. See `docs/releases/02.00.03.md` for an integration and recovery example.


## Container distribution checks

`docker-compose.yml` is a pull-only installer; keep its runtime settings aligned
with the source-build `compose.yaml`. `tests/test_container_release.py` checks
this contract, version metadata, registry errors and public artifact boundaries.
Build a disposable `kellmarks:ci` image, then run `python scripts/docker_smoke.py`
for source deployment and `KELLMARKS_TEST_COMPOSE=docker-compose.yml python
scripts/docker_smoke.py` for a downloaded-file-only installation. CI exercises
both Linux AMD64 and ARM64. Never run these tests against an operator volume.

Publishing is owned by the gated release workflow. Do not run
`scripts/publish_container.py` against production credentials outside that
workflow or repurpose an existing version tag. New versions must update VERSION,
application metadata, Docker/Compose defaults, guides, changelog and release
notes together. The release validator checks these markers. Changes to package
visibility remain an explicit owner action; record anonymous access separately.
