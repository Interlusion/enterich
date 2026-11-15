"""The fix stage's gate (ADR-008): a fix branch passes when it is an `auto/` branch whose
first commit is a `test:` and whose every other change comes right after its `test:`, whose
`test:` commits change only tests, which holds only commits of fixes a review accepted (the
run's `outcomes.json`, which `harness/outcomes.py` writes), changes no test file planned
for another branch (the run's `groups.json`, which `harness/plan.py` writes), no code or
changelog a branch that passed before it in the same call changes, only what the tests lens
may change and nothing the pipeline may not (a file moved away counts at its old place),
and passes every check, a secret scan of its commits and their messages and the
end-to-end tests included: none skipped, expected to fail or
left out, and every test `main` had where the branch left it still runs and passes, in as
many cases (only the operator removes, moves or weakens a test). Each branch is
checked in a worktree of its own; the results go to the run's `gates.jsonl`. With `--push`, a
branch that passed is pushed; one that passed earlier at the same commit is pushed without
a second run of the checks, so there is no reason to push past the gate. A push that fails
is recorded as not pushed, and the gate goes on. What is checked, recorded and pushed is
the commit the branch was at when the gate read it, wherever the branch has moved since. A
branch is compared with `main` as the remote has it (`origin/main`), fetched first: a local
`main` behind it would count commits merged since as the branch's own.

    E2E_ERPNEXT_URL=http://127.0.0.1:8080 \\
        uv run python harness/gate.py harness/runs/<date>-tests auto/tests-… [--base …] [--push]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Generator, Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
BASE = "origin/main"
COMMIT = re.compile(r"^(feat|fix|docs|ci|chore|refactor|test)(\([\w-]+\))?!?: \S")
# What the tests lens changes: tests, the code a test shows wrong, and the changelog line
# of that fix. Anything else is outside it, whatever it is called; another lens brings its own
ALLOWED = ("tests/", "src/enterich/", "CHANGELOG.md")
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
    # What the checks run and read: a branch could weaken the checks it is judged by
    "scripts/",
    ".mdformat.toml",
    "lychee.toml",
)
# Files the checks and the agents read wherever they lie, such as a ruff.toml in tests/
FORBIDDEN_NAMES = (
    "ruff.toml",
    ".ruff.toml",
    "pytest.ini",
    ".pytest.ini",
    "pytest.toml",
    ".pytest.toml",
    "tox.ini",
    "setup.cfg",
    "pyproject.toml",
    "pyrightconfig.json",
    ".mdformat.toml",
    "lychee.toml",
    ".lycheeignore",
    "AGENTS.md",
    "CLAUDE.md",
)
CHECKS = {
    "ruff": ["uv", "run", "ruff", "check"],
    "format": ["uv", "run", "ruff", "format", "--check"],
    "types": ["uv", "run", "basedpyright"],
    "markdown": ["uv", "run", "mdformat", "--check", "."],
    "links": ["scripts/check-links.sh"],
    # E2E_ERPNEXT_URL set: the end-to-end tests run with the others; -rp names each that passed
    "tests": ["uv", "run", "pytest", "-q", "-p", "no:cacheprovider", "-rp"],
}
# gitleaks as CI runs it, from the image it pins, on the branch's patch: the pipeline
# pushes to a public repository, and CI scans only pull requests and pushes to main
SCANNER_IMAGE_DIR = ".github/gitleaks"
SCANNER_IMAGE = "enterich-gate-gitleaks"
SCANNER = ["docker", "run", "--rm", "-i", SCANNER_IMAGE, "stdin", "--redact", "--no-banner"]
COLLECT = ["uv", "run", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
TEST = re.compile(r"^[\w./-]+\.py::\S")
PASSED = "PASSED "


def unreviewed(
    commits: list[tuple[str, str]], accepted: Sequence[str], patch_ids: Mapping[str, str]
) -> list[str]:
    """The subjects of a branch's commits (hash, subject) that are no commit of a fix a
    review accepted. An agent may have given the start of a hash; a commit whose diff is an
    accepted one's to the letter (`git patch-id --verbatim`) is that commit, moved when a
    rejected one was dropped."""

    def patch_id(commit: str) -> str | None:
        return next((p for h, p in patch_ids.items() if h.startswith(commit)), None)

    accepted_ids = {p for a in accepted if (p := patch_id(a))}
    return [
        subject
        for full, subject in commits
        if not any(full.startswith(a) for a in accepted) and patch_ids.get(full) not in accepted_ids
    ]


def beyond_tests(changes: Sequence[tuple[str, Sequence[str]]]) -> list[str]:
    """The `test:` commits (subject, paths) that change more than the tests."""
    return [
        subject
        for subject, paths in changes
        if subject.startswith("test") and any(not p.startswith("tests/") for p in paths)
    ]


def shared(paths: Iterable[str], passed: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """The paths outside the tests that a branch which passed before this one in the same
    call also changes, each with that branch: the second to merge would conflict. A branch
    that failed holds nothing back."""
    theirs = {p: branch for branch in reversed(list(passed)) for p in passed[branch]}
    return {p: theirs[p] for p in sorted(paths) if not p.startswith("tests/") and p in theirs}


def unproven(output: str) -> int:
    """How many tests pytest's last line says it skipped, expected to fail (whether they
    did or not) or left out. With the end-to-end site given, none is; such a test would
    pass the gate having proved nothing."""
    last = next((line for line in reversed(output.splitlines()) if line.strip()), "")
    counts = re.findall(r"(\d+) (?:skipped|xfailed|xpassed|deselected)", last)
    return sum(int(n) for n in counts)


def _function(test: str) -> str:
    """A test without its case: `tests/unit/test_a.py::test_b[1-x]` is `…::test_b`."""
    return test.partition("[")[0]


def tests_collected(output: str) -> Counter[str]:
    """The cases of each test function in `pytest --collect-only -q`'s output."""
    return Counter(_function(line) for line in output.splitlines() if TEST.match(line))


def tests_passed(output: str) -> Counter[str]:
    """The cases of each test function that passed, by pytest's `-rp` lines."""
    lines = output.splitlines()
    return Counter(
        _function(line.removeprefix(PASSED)) for line in lines if line.startswith(PASSED)
    )


def no_longer_passing(before: Mapping[str, int], passed: Mapping[str, int]) -> list[str]:
    """The test functions that pass in fewer cases than `main` had where the branch left
    it: removed, renamed, moved to where pytest doesn't look, skipped, expected to fail,
    left out by a hook, or with a case taken away. A new test or case is none of these."""
    return [
        f"{test} passes in {passed.get(test, 0)} of {cases} cases"
        for test, cases in sorted(before.items())
        if passed.get(test, 0) < cases
    ]


def passed_earlier(
    records: list[dict[str, Any]], branch: str, commit: str
) -> dict[str, bool] | None:
    """The checks of the branch's last record, if it passed at this very commit."""
    mine = [r for r in records if r.get("branch") == branch]
    if mine and mine[-1].get("commit") == commit and mine[-1].get("passed") is True:
        return cast("dict[str, bool]", mine[-1]["checks"])
    return None


def planned_elsewhere(groups: list[dict[str, Any]], branch: str) -> dict[str, str]:
    """The test files the run's plan gives to other branches, each with its branch."""
    return {
        cast("str", path): cast("str", g["branch"])
        for g in groups
        if g["branch"] != branch
        for path in cast("list[Any]", g["files"])
    }


def problems(
    branch: str,
    subjects: list[str],
    paths: list[str],
    unreviewed: Sequence[str] = (),
    elsewhere: Mapping[str, str] | None = None,
    *,
    beyond_tests: Sequence[str] = (),
    shared: Mapping[str, str] | None = None,
) -> list[str]:
    """What keeps a branch from the gate's checks: its name, its commits (oldest first),
    the paths it changes, those of its commits no review accepted, the test files the plan
    gives to another branch (`elsewhere`), its `test:` commits that change more than tests,
    and the paths a branch that passed before it changes (`shared`)."""
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
    found += [f"{s!r} is no commit of a fix a review accepted" for s in unreviewed]
    found += [
        f"{s!r} changes more than tests: the code comes in its own commit" for s in beyond_tests
    ]
    found += [f"{p} is planned for {(elsewhere or {})[p]}" for p in paths if p in (elsewhere or {})]
    found += [
        f"{p} is also changed by {other}: gate this branch after that one is merged"
        for p, other in (shared or {}).items()
    ]
    for path in paths:
        prefix = next((f for f in FORBIDDEN if path == f or path.startswith(f)), None)
        prefix = prefix or next((n for n in FORBIDDEN_NAMES if Path(path).name == n), None)
        if prefix:
            found.append(f"{path} is outside what the pipeline may change ({prefix})")
        elif not any(path == a or (a.endswith("/") and path.startswith(a)) for a in ALLOWED):
            found.append(f"{path} is outside what the tests lens changes ({', '.join(ALLOWED)})")
    return found


def _git(*args: str, repo: Path = ROOT, stdin: str | None = None) -> str:
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *args],  # noqa: S607 - git from PATH, as every script here
        cwd=repo,
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


@dataclass
class BranchState:
    """What the gate reads of a branch at one commit: its commits (hash, subject) oldest
    first, the paths it changes and each commit's. Without renames, so a file moved away
    shows at its old place too; each path as it is, whatever its name holds (`-z`)."""

    commits: list[tuple[str, str]]
    paths: list[str]
    changes: list[tuple[str, list[str]]]


def _paths(*args: str, repo: Path) -> list[str]:
    listed = _git(*args, "--no-renames", "--name-only", "-z", repo=repo)
    return [path for path in listed.split("\0") if path]


def branch_state(repo: Path, base: str, commit: str) -> BranchState:
    log = _git("log", "--reverse", "--format=%H %s", f"{base}..{commit}", repo=repo)
    commits = [
        (full, subject) for full, _, subject in (line.partition(" ") for line in log.splitlines())
    ]
    paths = _paths("diff", f"{base}...{commit}", repo=repo)
    changes = [
        (subject, _paths("diff-tree", "--no-commit-id", "-r", full, repo=repo))
        for full, subject in commits
    ]
    return BranchState(commits, sorted(paths), changes)


def patch_ids(commits: Sequence[str], repo: Path = ROOT) -> dict[str, str]:
    """Each commit's `git patch-id`: the same for the same diff, whatever its hash.
    Verbatim: in Python, the same lines at another indentation are another test."""
    found: dict[str, str] = {}
    for commit in commits:
        try:
            shown = _git("show", commit, repo=repo)
        except subprocess.CalledProcessError:
            continue  # a hash no longer in the repository
        line = _git("patch-id", "--verbatim", repo=repo, stdin=shown).split()
        if line:
            found[_git("rev-parse", commit, repo=repo).strip()] = line[0]
    return found


def patch(repo: Path, fork: str, commit: str) -> str:
    """What a push of the commit makes public beyond `main`: every commit since the fork,
    its message and its diff, a secret removed again included."""
    return _git("log", "-p", "--no-color", "--no-ext-diff", f"{fork}..{commit}", repo=repo)


def leaks(repo: Path, fork: str, commit: str, scanner: Sequence[str] = SCANNER) -> bool:
    """Whether the scanner finds a secret in the branch's patch; it says what, redacted."""
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        scanner, input=patch(repo, fork, commit), capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        print(
            f"{commit}: the secret scan failed\n{(done.stdout + done.stderr)[-3000:]}",
            file=sys.stderr,
        )
    return done.returncode != 0


def _scanner() -> None:
    """The scanner's image, built from the Dockerfile CI builds it from."""
    subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["docker", "build", "-q", "-t", SCANNER_IMAGE, SCANNER_IMAGE_DIR],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        check=True,
    )


@contextmanager
def _tree(commit: str) -> Generator[Path]:
    """A worktree of the commit with its packages, removed afterwards."""
    tree = Path(tempfile.mkdtemp(prefix="enterich-gate-"))
    try:
        _git("worktree", "add", "--detach", str(tree), commit)
        subprocess.run(["uv", "sync", "--locked", "-q"], cwd=tree, check=True)  # noqa: S607
        yield tree
    finally:
        _git("worktree", "remove", "--force", str(tree))
        shutil.rmtree(tree, ignore_errors=True)


def _tests_at(commit: str) -> Counter[str]:
    """The tests pytest finds at a commit, the end-to-end tests included."""
    with _tree(commit) as tree:
        done = subprocess.run(COLLECT, cwd=tree, capture_output=True, text=True, check=False)  # noqa: S603
    if done.returncode != 0:
        raise RuntimeError(f"pytest finds no tests at {commit}:\n{done.stdout[-2000:]}")
    return tests_collected(done.stdout)


def _checks(branch: str, commit: str, before: Mapping[str, int], fork: str) -> dict[str, bool]:
    """Every check at the commit; `before` is what the tests are compared with, the tests
    `main` had where the branch left it at `fork`."""
    results: dict[str, bool] = {"secrets": not leaks(ROOT, fork, commit)}
    with _tree(commit) as tree:
        for name, command in CHECKS.items():
            done = subprocess.run(command, cwd=tree, capture_output=True, text=True, check=False)  # noqa: S603
            results[name] = done.returncode == 0
            shown = "\n".join(
                line for line in done.stdout.splitlines() if not line.startswith(PASSED)
            )
            if name == "tests" and results[name]:
                gone = no_longer_passing(before, tests_passed(done.stdout))
                if left_out := unproven(done.stdout):
                    gone.append(f"{left_out} tests skipped, expected to fail or left out")
                if gone:
                    results[name] = False
                    shown = "every test must run and pass:\n" + "\n".join(gone)
            if not results[name]:
                print(f"{branch}: {name} failed\n{(shown + done.stderr)[-3000:]}", file=sys.stderr)
    return results


def fetch(repo: Path, base: str) -> None:
    """Brings a remote's branch (`origin/main`) up to date; a local base stays as it is."""
    remote, _, branch = base.partition("/")
    remotes = subprocess.run(
        ["git", "remote"],  # noqa: S607 - git from PATH, as every script here
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if branch and remote in remotes:
        subprocess.run(  # noqa: S603 - fixed arguments, no shell
            ["git", "fetch", "-q", remote, branch],  # noqa: S607 - git from PATH
            cwd=repo,
            check=True,
        )


def pushed(repo: Path, commit: str, branch: str) -> bool:
    """Pushes the commit as the branch and says whether that worked: a push the remote
    refuses, or one that doesn't reach it, is no reason to lose the gate's record."""
    try:
        _git("push", "origin", f"{commit}:refs/heads/{branch}", repo=repo)
    except subprocess.CalledProcessError as error:
        print(f"{branch}: the push failed\n{error.stderr}", file=sys.stderr)
        return False
    return True


def main(run: Path, branches: list[str], base: str, push: bool) -> int:
    if not os.environ.get("E2E_ERPNEXT_URL"):
        print("E2E_ERPNEXT_URL is not set: the gate runs the end-to-end tests", file=sys.stderr)
        return 2
    outcomes = run / "outcomes.json"
    if not outcomes.is_file():
        print(f"{outcomes} is missing: run harness/outcomes.py on the run first", file=sys.stderr)
        return 2
    plan = run / "groups.json"
    if not plan.is_file():
        print(f"{plan} is missing: run harness/plan.py on the run first", file=sys.stderr)
        return 2
    groups = cast("list[dict[str, Any]]", json.loads(plan.read_text()))
    fetch(ROOT, base)
    _scanner()
    summary = cast("dict[str, Any]", json.loads(outcomes.read_text()))
    if "accepted" not in summary:
        print(
            f"{outcomes} lists no accepted commits: run harness/outcomes.py again", file=sys.stderr
        )
        return 2
    accepted = cast("dict[str, list[str]]", summary["accepted"])
    results = run / "gates.jsonl"
    lines = results.read_text(encoding="utf-8").splitlines() if results.is_file() else []
    records = [cast("dict[str, Any]", json.loads(line)) for line in lines if line.strip()]
    # Each branch read once, at one commit: what is checked is what is pushed
    at = {branch: _git("rev-parse", branch).strip() for branch in branches}
    states = {branch: branch_state(ROOT, base, at[branch]) for branch in branches}
    passed_paths: dict[str, list[str]] = {}
    # The tests main had where a branch left it, read once per such commit
    forks: dict[str, Counter[str]] = {}

    def before(commit: str) -> Counter[str]:
        fork = _git("merge-base", base, commit).strip()
        if fork not in forks:
            forks[fork] = _tests_at(fork)
        return forks[fork]

    failed = 0
    with (run / "gates.jsonl").open("a", encoding="utf-8") as out:
        for branch in branches:
            commit, state = at[branch], states[branch]
            mine = accepted.get(branch, [])
            ids = patch_ids([*mine, *(full for full, _ in state.commits)])
            found = problems(
                branch,
                [subject for _, subject in state.commits],
                state.paths,
                unreviewed(state.commits, mine, ids),
                planned_elsewhere(groups, branch),
                beyond_tests=beyond_tests(state.changes),
                shared=shared(state.paths, passed_paths),
            )
            # The rules are checked every time; the checks once per commit when pushing
            earlier = passed_earlier(records, branch, commit) if push else None
            checks = (
                {}
                if found
                else earlier
                or _checks(branch, commit, before(commit), _git("merge-base", base, commit).strip())
            )
            passed = not found and all(checks.values())
            if passed:
                passed_paths[branch] = state.paths
            sent = passed and push and pushed(ROOT, commit, branch)
            failed += not passed or (push and not sent)
            record = {
                "branch": branch,
                "commit": commit,
                "problems": found,
                "checks": checks,
                "passed": passed,
                "pushed": sent,
            }
            out.write(json.dumps(record) + "\n")
            print(f"{branch}: {'passed' if passed else 'failed'}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The fix stage's gate (ADR-008)")
    parser.add_argument("run", type=Path)
    parser.add_argument("branches", nargs="+")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--push", action="store_true")
    a = parser.parse_args()
    sys.exit(main(a.run, a.branches, a.base, a.push))
