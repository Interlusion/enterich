"""The fix stage's gate (ADR-008): a fix branch passes when it is an `auto/` branch whose
first commit is a `test:` and whose every other change comes right after its `test:`,
changes nothing the pipeline may not change, and passes every
check, the end-to-end tests included. Each branch is checked in a worktree of its own;
the results go to the run's `gates.jsonl`. With `--push`, a branch that passed is pushed.

    E2E_ERPNEXT_URL=http://127.0.0.1:8080 \\
        uv run python harness/gate.py harness/runs/<date>-tests auto/tests-… [--base main] [--push]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMIT = re.compile(r"^(feat|fix|docs|ci|chore|refactor|test)(\([\w-]+\))?!?: \S")
# ADR-008's Compliance list; the tool-list snapshot changes only with its spec, and the
# pipeline doesn't change its own scripts, the operator's suppressions or its workflows
FORBIDDEN = (
    "docs/specs/",
    "docs/arc42/adr/",
    "AGENTS.md",
    "CLAUDE.md",
    ".github/",
    "Dockerfile",
    "server.json",
    "pyproject.toml",
    "uv.lock",
    "tests/snapshots/",
    "harness/",
    ".claude/",
)
CHECKS = {
    "ruff": ["uv", "run", "ruff", "check"],
    "format": ["uv", "run", "ruff", "format", "--check"],
    "types": ["uv", "run", "basedpyright"],
    "markdown": ["uv", "run", "mdformat", "--check", "."],
    "links": ["scripts/check-links.sh"],
    # E2E_ERPNEXT_URL set: the end-to-end tests run with the others
    "tests": ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider"],
}


def problems(branch: str, subjects: list[str], paths: list[str]) -> list[str]:
    """What keeps a branch from the gate's checks: its name, its commits (oldest first),
    the paths it changes."""
    found: list[str] = []
    if not branch.startswith("auto/"):
        found.append(f"{branch} is not an auto/ branch")
    if not subjects:
        return [*found, "no commits"]
    found += [f"{s!r} is not a Conventional Commit" for s in subjects if not COMMIT.match(s)]
    if not subjects[0].startswith("test"):
        found.append("the first commit is not a test: first, the failing test")
    # A survey's branch holds one finding after another: each change right after its test
    found += [
        f"{s!r} is not a fix:, feat: or refactor: right after its test: commit"
        for before, s in pairwise(subjects)
        if not s.startswith("test")
        and not (before.startswith("test") and s.startswith(("fix", "feat", "refactor")))
    ]
    for path in paths:
        if prefix := next((f for f in FORBIDDEN if path == f or path.startswith(f)), None):
            found.append(f"{path} is outside what the pipeline may change ({prefix})")
    return found


def _git(*args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *args],  # noqa: S607 - git from PATH, as every script here
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def _checks(branch: str) -> dict[str, bool]:
    tree = Path(tempfile.mkdtemp(prefix="enterich-gate-"))
    try:
        _git("worktree", "add", "--detach", str(tree), branch)
        subprocess.run(["uv", "sync", "--locked", "-q"], cwd=tree, check=True)  # noqa: S607
        results: dict[str, bool] = {}
        for name, command in CHECKS.items():
            done = subprocess.run(command, cwd=tree, capture_output=True, text=True, check=False)  # noqa: S603
            results[name] = done.returncode == 0
            if not results[name]:
                print(
                    f"{branch}: {name} failed\n{(done.stdout + done.stderr)[-3000:]}",
                    file=sys.stderr,
                )
        return results
    finally:
        _git("worktree", "remove", "--force", str(tree))
        shutil.rmtree(tree, ignore_errors=True)


def main(run: Path, branches: list[str], base: str, push: bool) -> int:
    if not os.environ.get("E2E_ERPNEXT_URL"):
        print("E2E_ERPNEXT_URL is not set: the gate runs the end-to-end tests", file=sys.stderr)
        return 2
    failed = 0
    with (run / "gates.jsonl").open("a", encoding="utf-8") as out:
        for branch in branches:
            subjects = _git("log", "--reverse", "--format=%s", f"{base}..{branch}").splitlines()
            paths = _git("diff", "--name-only", f"{base}...{branch}").splitlines()
            found = problems(branch, subjects, paths)
            checks = {} if found else _checks(branch)
            passed = not found and all(checks.values())
            if passed and push:
                _git("push", "--set-upstream", "origin", branch)
            failed += not passed
            record = {
                "branch": branch,
                "commit": _git("rev-parse", branch).strip(),
                "problems": found,
                "checks": checks,
                "passed": passed,
                "pushed": passed and push,
            }
            out.write(json.dumps(record) + "\n")
            print(f"{branch}: {'passed' if passed else 'failed'}")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The fix stage's gate (ADR-008)")
    parser.add_argument("run", type=Path)
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--base", default="main")
    parser.add_argument("--push", action="store_true")
    a = parser.parse_args()
    sys.exit(main(a.run, a.branches, a.base, a.push))
