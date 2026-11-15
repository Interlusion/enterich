"""The fix stage's cleanup (ADR-008): finds the worktrees under `.claude/worktrees/` that the
fix workflow's agents are done with, and the `worktree-<name>` branches made for them, and
with `--remove` removes them. A worktree is done with when it isn't locked, holds no
uncommitted change, and its commits are on an `auto/` branch, so nothing is lost. One
without commits counts only once the workflow has ended (`--finished`): an agent may be
starting in it. A worktree whose folder is gone is taken off git's list under the same rule:
its commits are on an `auto/` branch, or it has none. One git refuses to remove (it
changed since the survey) keeps its branch, and the rest go on. No other worktree of the
repository is touched. Without `--remove` it only lists what it would do.

A running agent's worktree is locked for as long as the agent runs (Claude Code locks it
with the agent's process), so one that is not locked holds no agent at work.

Its base is `main` as the remote has it (`origin/main`), fetched first.

    uv run python harness/cleanup.py [--base origin/main] [--finished] [--remove]
"""

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from harness.gate import BASE, fetch
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    from gate import BASE, fetch  # type: ignore[import-not-found, no-redef]

ROOT = Path(__file__).resolve().parent.parent
TREES = Path(".claude") / "worktrees"


@dataclass
class Found:
    worktrees: list[Path] = field(default_factory=list[Path])
    missing: list[Path] = field(default_factory=list[Path])
    branches: list[str] = field(default_factory=list[str])
    kept: list[tuple[Path, str]] = field(default_factory=list[tuple[Path, str]])


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *args],  # noqa: S607 - git from PATH, as every script here
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _listed(root: Path) -> list[dict[str, str]]:
    """`git worktree list --porcelain`: one record per worktree, a line's first word its key."""
    listed: list[dict[str, str]] = []
    for block in _git(root, "worktree", "list", "--porcelain").stdout.strip().split("\n\n"):
        entry: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            entry[key] = value
        listed.append(entry)
    return listed


def _why_kept(
    root: Path, tree: Path, entry: dict[str, str], base: str, finished: bool
) -> str | None:
    head = entry["HEAD"]
    gone = not tree.is_dir()
    if "locked" in entry:
        return "locked: an agent is running in it"
    if not gone and _git(tree, "status", "--porcelain").stdout.strip():
        return "uncommitted changes"
    if _git(root, "merge-base", "--is-ancestor", head, base, check=False).returncode == 0:
        return None if finished or gone else "no commits: an agent may be starting in it"
    if not _git(root, "branch", "--list", "auto/*", "--contains", head).stdout.strip():
        return "its commits are on no auto/ branch"
    return None


def survey(root: Path, base: str, finished: bool = False) -> Found:
    """What can go: the workflow's worktrees that are done with, each with the branch made
    for it if that branch holds nothing of its own; and what stays, with why."""
    found = Found()
    trees = (root / TREES).resolve()
    listed = _listed(root)
    for entry in listed:
        tree = Path(entry["worktree"])
        if trees not in tree.resolve().parents:
            continue
        if why := _why_kept(root, tree, entry, base, finished):
            found.kept.append((tree, why))
            continue
        if not tree.is_dir():
            # Deleted by hand or by a crashed agent: git lists it until it is taken off
            found.missing.append(tree)
        else:
            found.worktrees.append(tree)
        branch = f"worktree-{tree.name}"
        exists = _git(root, "rev-parse", "-q", "--verify", f"refs/heads/{branch}", check=False)
        checked_out = any(
            e.get("branch") == f"refs/heads/{branch}" and Path(e["worktree"]) != tree
            for e in listed
        )
        merged = _git(root, "merge-base", "--is-ancestor", branch, base, check=False)
        if exists.returncode == 0 and merged.returncode == 0 and not checked_out:
            found.branches.append(branch)
    found.worktrees.sort()
    found.missing.sort()
    found.branches.sort()
    found.kept.sort()
    return found


def clear(root: Path, found: Found) -> list[Path]:
    """Removes what the survey found and returns the worktrees removed. Without --force git
    refuses a worktree that changed since the survey: it stays with its branch, and the
    rest go on. The missing are taken off git's list one by one: `git worktree prune`
    would take every missing worktree of the repository, the operator's too."""
    removed: list[Path] = []
    for tree in [*found.worktrees, *found.missing]:
        done = _git(root, "worktree", "remove", str(tree), check=False)
        if done.returncode == 0:
            removed.append(tree)
            print(f"removed {tree.relative_to(root)}")
        else:
            print(f"kept {tree.relative_to(root)}: {done.stderr.strip()}", file=sys.stderr)
    gone = {f"worktree-{tree.name}" for tree in removed}
    for branch in found.branches:
        if branch in gone:
            _git(root, "branch", "-D", branch)
            print(f"deleted branch {branch}")
    return removed


def main(root: Path, base: str, remove: bool, finished: bool) -> int:
    fetch(root, base)
    found = survey(root, base, finished)
    for tree, why in found.kept:
        print(f"keep {tree.relative_to(root)}: {why}")
    if remove:
        clear(root, found)
        return 0
    for tree in found.worktrees:
        print(f"would remove {tree.relative_to(root)}")
    for tree in found.missing:
        print(f"would remove {tree.relative_to(root)} from git's list: its folder is gone")
    for branch in found.branches:
        print(f"would delete branch {branch}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The fix stage's cleanup (ADR-008)")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--finished", action="store_true")
    parser.add_argument("--remove", action="store_true")
    a = parser.parse_args()
    sys.exit(main(ROOT, a.base, a.remove, a.finished))
