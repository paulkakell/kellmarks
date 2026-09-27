"""One-release maintenance executor; removed from the prepared release tree."""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

REPO = "paulkakell/kellmarks"
BASE = "816931588597236626563e32a8199a090fbe7a2a"
DEV = "313efe008e27a7cba4f3e6e01944283c926d0ac3"
BRANCH = "release/02.00.03"
VERSION = "02.00.03"
OLD_VERSION = "02.00.02"
WORKFLOW = ".github/workflows/consolidate-020003.yml"
SCRIPT = "scripts/prepare_020003.py"
CHECKOUT_OLD = "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5"
CHECKOUT_NEW = "3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1"
PYTHON_OLD = "ece7cb06caefa5fff74198d8649806c4678c61a1 # v6"
PYTHON_NEW = "5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0"
CODEQL_OLD = "ff2f1c621b7f889edc0d3c761ac2e6a3f8cdb0dd"
CODEQL_NEW = "db488ddef3bf6cb639b32c2e9a7c0a7ea8271d28"
SOURCES = [
    (2, "dependabot/github_actions/dev/actions/checkout-7.0.1", "a54d551201b7b9df6e59cdede2dfac2bda48e742", CHECKOUT_OLD, CHECKOUT_NEW,
     [".github/workflows/ci.yml", ".github/workflows/codeql.yml", ".github/workflows/release.yml"]),
    (3, "dependabot/github_actions/dev/actions/setup-python-7.0.0", "8e100e5f8da0638262bd7631aa9bca273c751d46", PYTHON_OLD, PYTHON_NEW,
     [".github/workflows/ci.yml"]),
    (4, "dependabot/github_actions/dev/github/codeql-action/autobuild-4.37.8", "1ad30c4720589fd1101f799a2160498fa7390187",
     "github/codeql-action/autobuild@" + CODEQL_OLD, "github/codeql-action/autobuild@" + CODEQL_NEW, [".github/workflows/codeql.yml"]),
    (5, "dependabot/github_actions/dev/github/codeql-action/init-4.37.8", "5de31aa55495872299965820595c2388c3b882e1",
     "github/codeql-action/init@" + CODEQL_OLD, "github/codeql-action/init@" + CODEQL_NEW, [".github/workflows/codeql.yml"]),
    (6, "dependabot/github_actions/dev/github/codeql-action/analyze-4.37.8", "aac043927b3c6324b0d22e0101609e49498d47f8",
     "github/codeql-action/analyze@" + CODEQL_OLD, "github/codeql-action/analyze@" + CODEQL_NEW, [".github/workflows/codeql.yml"]),
]
REQUIRED = {
    "Tests on Python 3.10", "Tests on Python 3.13",
    "Quality, security, dependencies, and clean build",
    "Analyze python", "Analyze javascript-typescript",
}


def run(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(args, input=input_text, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def api(path: str, *args: str):
    text = run("gh", "api", f"repos/{REPO}/{path}", *args)
    return json.loads(text) if text else None


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def remote_sha(branch: str) -> str:
    lines = run("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}").splitlines()
    require(len(lines) == 1, f"missing or ambiguous branch: {branch}")
    return lines[0].split()[0]


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    require(old in text, f"expected source marker missing: {path}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def require_ancestor(older: str, newer: str) -> None:
    run("git", "merge-base", "--is-ancestor", older, newer)


def prepare() -> None:
    starting = run("git", "rev-parse", "HEAD")
    require(remote_sha(BRANCH) == starting, "release branch moved; re-review before preparing")
    require(remote_sha("main") == BASE, "main moved; re-review before preparing")
    require(run("git", "diff", "--name-only", DEV, BASE) == "", "base trees differ")
    require(Path("VERSION").read_text().strip() == OLD_VERSION, "unexpected baseline version")
    require_ancestor(BASE, starting)
    for number, branch, sha, old, new, paths in SOURCES:
        require(remote_sha(branch) == sha, f"PR #{number} head changed")
        pr = api(f"pulls/{number}")
        require(pr["state"] == "open" and not pr["draft"], f"PR #{number} is not ready")
        require(pr["head"]["sha"] == sha and pr["base"]["ref"] == "dev", f"PR #{number} refs changed")
        require(pr["head"]["repo"]["full_name"] == REPO, "unexpected source repository")
        changed = run("git", "diff", "--name-only", DEV, sha).splitlines()
        require(sorted(changed) == sorted(paths), f"unexpected files in PR #{number}")
        for path in paths:
            baseline = run("git", "show", f"{DEV}:{path}")
            actual = run("git", "show", f"{sha}:{path}")
            require(old in baseline and baseline.replace(old, new) == actual,
                    f"unexpected patch in PR #{number}: {path}")
            replace(path, old, new)

    current_files = [
        "VERSION", "docs/server/app.py", "docs/assets/app.js", "README.md",
        "docs/server/README.md", "docs/API.md", "docs/SECURITY_ARCHITECTURE.md",
        "docs/index.html", "docs/openapi.yaml", "docs/server/requirements.lock",
        "scripts/validate_release.py",
    ]
    for path in current_files:
        replace(path, OLD_VERSION, VERSION)
    replace("tests/test_release_metadata.py", 'assert version == "02.00.02"', 'assert version == "02.00.03"')
    replace("SECURITY.md", "| 02.00.02 | Yes |", "| 02.00.03 | Yes |\n| 02.00.02 | Yes |")

    dependabot = Path(".github/dependabot.yml")
    text = dependabot.read_text(encoding="utf-8")
    require(text.count("package-ecosystem: github-actions") == 1, "unexpected Dependabot configuration")
    text += '    groups:\n      codeql:\n        patterns:\n          - "github/codeql-action/*"\n'
    dependabot.write_text(text, encoding="utf-8")

    validation = '''    codeql_pins = re.findall(
        r"uses:\\s+github/codeql-action/(?:init|autobuild|analyze)@([0-9a-f]{40})",
        read(".github/workflows/codeql.yml"),
    )
    if len(codeql_pins) != 3 or len(set(codeql_pins)) != 1:
        fail("CodeQL init, autobuild, and analyze must use the same immutable revision")

'''
    replace("scripts/validate_release.py", '    environment_example = read(".env.example")', validation + '    environment_example = read(".env.example")')

    tests = r'''

def test_codeql_steps_use_one_immutable_revision() -> None:
    steps = re.findall(
        r"uses:\s+github/codeql-action/(init|autobuild|analyze)@([0-9a-f]{40})",
        read(".github/workflows/codeql.yml"),
    )
    assert sorted(name for name, _ in steps) == ["analyze", "autobuild", "init"]
    assert len({revision for _, revision in steps}) == 1


def test_dependabot_groups_codeql_updates() -> None:
    configuration = read(".github/dependabot.yml")
    actions = configuration.split("package-ecosystem: github-actions", 1)[1]
    assert "target-branch: dev" in actions
    assert re.search(r"(?m)^    groups:\n      codeql:\n        patterns:\n", actions)
    assert '- "github/codeql-action/*"' in actions


def test_020003_preparation_files_are_absent() -> None:
    assert not (ROOT / ".github/workflows/consolidate-020003.yml").exists()
    assert not (ROOT / "scripts/prepare_020003.py").exists()
'''
    with Path("tests/test_release_metadata.py").open("a", encoding="utf-8") as stream:
        stream.write(tests)

    entry = '''## [02.00.03] - 2026-09-27

### Fixed

- Integrate the five outstanding workflow updates from PRs #2, #3, #4, #5, and #6 without discarding their commit ancestry.
- Update pinned actions/checkout to 7.0.1 and actions/setup-python to 7.0.0.
- Update CodeQL init, autobuild, and analyze together to 4.37.8. Separate updates failed with a configuration-version mismatch.
- Group future CodeQL Dependabot updates and reject mixed CodeQL revisions in release validation and regression tests.
- Align release metadata, badges, API documentation, and supported-version documentation with 02.00.03.

### Maintenance and compatibility

- Preserve main and the documented dev integration branch. Remove only incorporated, unchanged short-lived branches after release checks succeed.
- No application API, configuration-default, runtime dependency, data-schema, or migration behavior changes. Classification: fix, with additive validation and documentation.
- Rollback baseline: 816931588597236626563e32a8199a090fbe7a2a. Source commit ledger and rollback instructions are in docs/releases/02.00.03.md.

'''
    changelog = Path("CHANGELOG.md")
    old = changelog.read_text(encoding="utf-8")
    require("## [02.00.02]" in old and "## [02.00.03]" not in old, "unexpected changelog")
    changelog.write_text(old.replace("## [02.00.02]", entry + "## [02.00.02]", 1), encoding="utf-8")

    notes = '''# Kellmarks 02.00.03

## Release classification

Patch release: CI maintenance and branch consolidation. Adds regression validation and contributor guidance. No application behavior, API contract, configuration defaults, runtime dependency versions, storage schema, or database migration changes.

## Included work and reason

Integrates PRs #2 through #6 while retaining all five source commits as merge ancestors. actions/checkout is pinned to 7.0.1 and actions/setup-python to 7.0.0. All three CodeQL actions are pinned to the same 4.37.8 revision. The previous separate CodeQL PR checks failed because init, autobuild, and analyze loaded different configuration versions, not because their application tests failed.

The GitHub-hosted CI configuration does not use setup-python's removed pip-install input. Checkout remains SHA-pinned and does not enable unsafe pull-request checkout. Existing least-privilege CI and security-scanning permissions remain unchanged.

## Source ledger

| Source | Original commit |
| --- | --- |
| main rollback baseline | 816931588597236626563e32a8199a090fbe7a2a |
| dev baseline, already contained in main | 313efe008e27a7cba4f3e6e01944283c926d0ac3 |
| PR #2, checkout | a54d551201b7b9df6e59cdede2dfac2bda48e742 |
| PR #3, setup-python | 8e100e5f8da0638262bd7631aa9bca273c751d46 |
| PR #4, CodeQL autobuild | 1ad30c4720589fd1101f799a2160498fa7390187 |
| PR #5, CodeQL init | 5de31aa55495872299965820595c2388c3b882e1 |
| PR #6, CodeQL analyze | aac043927b3c6324b0d22e0101609e49498d47f8 |

Original branch names and commits are retained in docs/releases/02.00.03-branches.json for recovery. Historical releases and migration-backup names remain unchanged.

## Validation and release gates

The existing Security and quality workflow runs the full unit, integration, and regression suite on Python 3.10 and 3.13, with an 85 percent branch-aware coverage floor. Its quality job checks Ruff, mypy, Bandit, secret patterns, pinned runtime dependencies with pip-audit, pip compatibility, release configuration, JavaScript syntax, compilation, the benchmark, and a fresh-process health check. The CodeQL workflow analyzes Python and JavaScript/TypeScript.

Three regression tests cover matching CodeQL revisions, grouped dependency updates, and removal of temporary preparation files. Release validation now rejects mismatched CodeQL revisions. The release publisher requires all five named checks to succeed for the exact release commit before creating v02.00.03. Check-run records are the authoritative execution results; this document does not substitute planned checks for completed checks.

Runtime dependencies are unchanged, so their lock is not regenerated; only the release-identification comment changes. Authentication, authorization, input-validation paths, structured logging, and persistence logic are unchanged apart from the application version constant. No schema migration or new environment variables are introduced. The existing regression suite and benchmark remain release gates. No production load test or external alert-delivery verification is implied.

## Branch policy and examples

main remains the release branch. dev remains the contribution and Dependabot target. An inactive development branch is not deleted merely because its commits already exist in main. After integration, dev is fast-forwarded to main without rewriting history.

CodeQL updates must stay together. Dependabot now groups github/codeql-action/* in one pull request. Before merging a future update, run python scripts/validate_release.py and the required CI checks. Updating only one of init, autobuild, or analyze should fail validation.

Cleanup is restricted to the five audited Dependabot branches and the temporary release branch. Each must be unprotected, incorporated in both main and dev, and unchanged at its recorded head. Open dependent pull requests block deletion. The cleanup uses explicit branch names and expected-head leases, never a wildcard delete.

## Rollback and recovery

The previous main artifact remains reachable at commit 816931588597236626563e32a8199a090fbe7a2a and through the retained release history. For application rollback, redeploy that source commit. Since this patch does not change data schema 2 or runtime behavior, it does not require a data downgrade. Keep the current private data file and its backups; do not replace live data with sample data.

For a repository rollback, create a reviewed revert of the final integration merge using its first parent and assign a new patch version. Do not move an existing release tag or force-reset main. A deleted source branch can be restored at the exact commit in the source ledger, for example:

```bash
git fetch origin
git branch restored-checkout a54d551201b7b9df6e59cdede2dfac2bda48e742
git push origin restored-checkout
```

The maintenance executor verifies the rollback commit remains an ancestor before cleanup. These instructions concern source recovery; no production deployment rollback has been executed.

## Commit notes

```text
fix(02.00.03): consolidate dependency branches and align CodeQL actions

Integrate PRs #2, #3, #4, #5, and #6 with original commit ancestry.
Pin checkout 7.0.1, setup-python 7.0.0, and all CodeQL steps 4.37.8.
Group future CodeQL dependency updates and add mismatch regression checks.
Update version metadata, changelog, documentation, and rollback ledger.
Retain main/dev; prune only verified incorporated short-lived branches.

Classification: fix with additive validation; no application breaking changes.
Data schema: unchanged at 2. Runtime dependency versions: unchanged.
```
'''
    Path("docs/releases/02.00.03.md").write_text(notes, encoding="utf-8")
    ledger = {"version": VERSION, "rollback": BASE, "dev_baseline": DEV,
              "sources": [{"pull_request": number, "branch": branch, "sha": sha}
                          for number, branch, sha, *_ in SOURCES]}
    Path("docs/releases/02.00.03-branches.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    with Path("CONTRIBUTING.md").open("a", encoding="utf-8") as stream:
        stream.write('''
## Branch integration and cleanup

Keep main for releases and dev for contributions and dependency updates. Consolidate related updates on a versioned release branch, require all tests and security checks, then merge to main and fast-forward dev. Never infer that a long-lived branch is obsolete solely from age or commit containment.

CodeQL init, autobuild, and analyze must share one full commit SHA. Dependabot groups github/codeql-action/* to keep these updates together. Run `python scripts/validate_release.py` to reject mixed versions before opening a release PR.

After a release, remove only short-lived branches whose recorded tips are unchanged, unprotected, and ancestors of both main and dev, with no open dependent pull requests. Preserve a source-commit ledger in release notes. See `docs/releases/02.00.03.md` for an integration and recovery example.
''')
    Path(WORKFLOW).unlink()
    Path(SCRIPT).unlink()
    run("python", "scripts/validate_release.py")
    run("python", "-m", "compileall", "-q", "docs/server", "tests", "scripts")
    run("node", "--check", "docs/assets/app.js")
    run("git", "diff", "--check")
    run("git", "add", "--update")
    run("git", "add", "docs/releases/02.00.03.md", "docs/releases/02.00.03-branches.json")
    tree = run("git", "write-tree")
    parents = ["-p", starting]
    for _, _, sha, *_ in SOURCES:
        parents.extend(["-p", sha])
    message = (
        "fix(02.00.03): consolidate dependency branches and align CodeQL actions\n\n"
        "Integrate PRs #2, #3, #4, #5, and #6 with original commit ancestry.\n"
        "Group CodeQL updates, add regression checks, and align release metadata.\n"
        "No application API, runtime dependency, or data-schema changes.\n"
    )
    commit = run("git", "commit-tree", tree, *parents, input_text=message)
    require(remote_sha(BRANCH) == starting, "release branch moved before publication")
    run("git", "push", "origin", f"{commit}:refs/heads/{BRANCH}")
    print(json.dumps({"operation": "prepared", "version": VERSION, "commit": commit, "parents": [starting] + [item[2] for item in SOURCES]}))


def cleanup() -> None:
    main = remote_sha("main")
    require(remote_sha("dev") == main, "dev must be fast-forwarded to the release first")
    run("git", "fetch", "origin", "main", "dev", f"refs/tags/v{VERSION}:refs/tags/v{VERSION}")
    tagged = run("git", "rev-list", "-n", "1", f"v{VERSION}")
    require(tagged == main, "cleanup requires the published release at current main")
    require(api(f"releases/tags/v{VERSION}")["draft"] is False, "release is not published")
    require(run("git", "show", f"{main}:VERSION") == VERSION, "unexpected release version")
    require_ancestor(BASE, main)
    checks = api(f"commits/{main}/check-runs?per_page=100")["check_runs"]
    latest = {}
    for check in checks:
        name = check["name"]
        if name not in latest or check["id"] > latest[name]["id"]:
            latest[name] = check
    require(all(name in latest and latest[name]["conclusion"] == "success" for name in REQUIRED),
            "exact release commit does not have all successful checks")
    release_prs = api(f"pulls?state=closed&base=main&head=paulkakell:{BRANCH}&per_page=100")
    matches = [pr for pr in release_prs if pr.get("merged_at") and pr.get("merge_commit_sha") == main]
    require(len(matches) == 1, "cannot establish the merged release pull request")
    release_pr = matches[0]
    candidates = [(number, branch, sha) for number, branch, sha, *_ in SOURCES]
    candidates.append((release_pr["number"], BRANCH, release_pr["head"]["sha"]))
    planned = []
    for number, branch, sha in candidates:
        require(branch not in {"main", "dev"}, "long-lived branches may not be deleted")
        live = run("git", "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
        if not live:
            print(json.dumps({"branch": branch, "status": "already absent"}))
            continue
        require(remote_sha(branch) == sha, f"branch moved; retaining {branch}")
        metadata = api("branches/" + branch.replace("/", "%2F"))
        require(not metadata["protected"], f"protected branch: {branch}")
        require_ancestor(sha, main)
        pr = api(f"pulls/{number}")
        require(pr["head"]["sha"] == sha and pr["head"]["ref"] == branch, "PR head changed")
        planned.append((number, branch, sha, pr))
    open_prs = api("pulls?state=open&per_page=100")
    require(len(open_prs) < 100, "paginate open PRs before cleanup")
    for number, branch, _, _ in planned:
        dependencies = [pr["number"] for pr in open_prs if pr["number"] != number and
                        (pr["head"]["ref"] == branch or pr["base"]["ref"] == branch)]
        require(not dependencies, f"open PRs depend on {branch}: {dependencies}")
    for number, branch, sha, pr in planned:
        if pr["state"] == "open":
            api(f"issues/{number}/comments", "-X", "POST", "-f",
                f"body=Integrated with original commit ancestry in #{release_pr['number']} and v{VERSION}. Exact release checks passed. Closing the incorporated source PR before removing its unchanged branch.")
            api(f"pulls/{number}", "-X", "PATCH", "-f", "state=closed")
        require(remote_sha("main") == main and remote_sha("dev") == main, "release refs moved during cleanup")
        run("git", "push", f"--force-with-lease=refs/heads/{branch}:{sha}", "origin", f":refs/heads/{branch}")
        print(json.dumps({"operation": "deleted", "branch": branch, "preserved_commit": sha}))
    print(json.dumps({"operation": "cleanup complete", "release": main, "version": VERSION}))


if __name__ == "__main__":
    require(os.environ.get("GITHUB_REPOSITORY") == REPO, "unexpected repository")
    require(os.environ.get("GITHUB_REF") == f"refs/heads/{BRANCH}", "unexpected workflow ref")
    if int(os.environ["GITHUB_RUN_ATTEMPT"]) == 1:
        prepare()
    else:
        cleanup()
