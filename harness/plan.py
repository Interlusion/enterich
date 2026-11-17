"""The fix stage's plan (ADR-008): groups a run's fixes so that no two branches plan the same
test file. Fixes share a branch when their verdicts name a test file in common or when they
follow one ratchet; a fix whose verdict names no file stays with its survey. Writes
`groups.json`, the fix workflow's `groups` argument: per branch its files, its ratchets,
which go first, and its fixes. The gate refuses a branch that changes a file planned for
another. Planning a run again takes up what is left: a fix with an outcome in
`outcomes.jsonl` isn't planned, a ratchet with one isn't run again, and the findings of a
ratchet no review accepted are planned as fixes of their own. A fix whose agent found its
test belongs in another branch's file is planned once more in that file, and one its agent
found closed by an earlier test is planned once more if a fix on its branch was rejected, as
that test may be gone. A test file that an accepted fix changed stays with that fix's
branch, which holds its commits, and so do the fixes naming it; the branch of a fix no
review accepted is named, as its commits are dropped before the next fix stage.
Deterministic.

    uv run python harness/plan.py harness/runs/<date>-tests
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, cast

try:
    from harness import project
    from harness.jsonl import read as _records
    from harness.outcomes import NOT_ACCEPTED, state
    from harness.triage import lens as lens_of
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import project  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]
    from outcomes import NOT_ACCEPTED, state  # type: ignore[import-not-found, no-redef]
    from triage import lens as lens_of  # type: ignore[import-not-found, no-redef]

Node = tuple[str, str]
TEST_FILE = re.compile(rf"\b{re.escape(project.SOURCES['tests'])}/[\w/]+\.py\b")


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _files(fix: dict[str, Any]) -> list[str]:
    return cast("list[str]", fix["verdict"].get("test_files") or [])


def _name(files: list[str], ratchets: list[dict[str, Any]], origin: str) -> str:
    """A branch's name after `auto/<lens>-`: its first ratchet, else its first file with its
    directory (`unit-shapes`), else the survey its fixes came from."""
    if ratchets:
        return cast("str", ratchets[0]["slug"])
    if files:
        path = Path(files[0])
        return _slug(f"{path.parent.name} {path.stem.removeprefix('test_')}")
    return _slug(origin.removesuffix(".md"))


def groups(
    fixes: list[dict[str, Any]],
    ratchets: list[dict[str, Any]],
    before: dict[str, str] | None = None,
    lens: str = "tests",
) -> list[dict[str, Any]]:
    """The fixes in groups that share no test file: what a fix's verdict names ties it to
    the others naming it, a ratchet ties its findings together. A file an accepted fix
    changed (`before`, file to branch) ties its fixes to the others of that branch, and
    the group keeps the branch; one with files of several names the others in `also`."""
    parent: dict[Node, Node] = {}
    known = before or {}

    def find(node: Node) -> Node:
        while parent.setdefault(node, node) != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for fix in fixes:
        me = find(("fix", fix["key"]))
        ties: list[Node] = [("file", path) for path in _files(fix)]
        ties = ties or [("survey", cast("str", fix["origin"]))]
        ties += [("branch", known[path]) for path in _files(fix) if path in known]
        if fix.get("ratchet"):
            ties.append(("ratchet", f"ratchet:{fix['ratchet']}"))
        for tie in ties:
            parent[find(tie)] = me
            me = find(me)
    together: dict[Node, list[dict[str, Any]]] = {}
    for fix in fixes:
        together.setdefault(find(("fix", fix["key"])), []).append(fix)
    planned: list[dict[str, Any]] = []
    for members in together.values():
        members.sort(key=lambda f: cast("str", f["key"]))
        files = sorted({path for f in members for path in _files(f)})
        named = {f"ratchet:{f['ratchet']}" for f in members if f.get("ratchet")}
        first = sorted((r for r in ratchets if r["key"] in named), key=lambda r: r["key"])
        earlier = sorted({known[f] for f in files if f in known})
        name = f"auto/{lens}-{_name(files, first, cast('str', members[0]['origin']))}"
        # A ratchet a review accepted earlier isn't run again: its test is on the branch
        done = {r["key"] for r in first if not r.get("run", True)}
        planned.append(
            {
                "branch": earlier[0] if earlier else name,
                "also": earlier[1:],
                "files": files,
                "ratchets": [
                    {"key": r["key"], "slug": r["slug"]} for r in first if r.get("run", True)
                ],
                "fixes": [
                    {
                        "key": f["key"],
                        "slug": f["slug"],
                        "ratchet": f"ratchet:{f['ratchet']}" if f.get("ratchet") else None,
                        "ratchet_done": f"ratchet:{f.get('ratchet')}" in done,
                    }
                    for f in members
                ],
            }
        )
    planned.sort(key=lambda g: cast("str", g["branch"]))
    branches = [g["branch"] for g in planned]
    if twice := sorted({b for b in branches if branches.count(b) > 1}):
        raise ValueError(f"two groups would share a branch: {', '.join(twice)}")
    return planned


def taken_up(ended: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The fixes with an outcome that are planned once more, each with the test files its
    agent named: one whose test belongs in another branch's file, and one refuted on a
    branch where a fix was rejected. One planned once more already (`replaced`,
    which `harness/record.py` writes) keeps its second outcome."""
    rejected_on = {r.get("branch") for r in ended if state(r) in NOT_ACCEPTED}
    found: dict[str, list[str]] = {}
    for r in ended:
        if r.get("replaced"):
            continue
        notes = str(cast("dict[str, Any]", r.get("fixed") or {}).get("notes") or "")
        if state(r) == "elsewhere" and (named := TEST_FILE.findall(notes)):
            found[cast("str", r["key"])] = sorted(set(named))
        elif state(r) == "refuted" and r.get("branch") in rejected_on:
            found[cast("str", r["key"])] = []
    return found


def held(ended: list[dict[str, Any]]) -> dict[str, str]:
    """Each test file an accepted fix changed, with that fix's branch."""
    found: dict[str, str] = {}
    for r in ended:
        if state(r) != "accepted":
            continue
        fixed = cast("dict[str, Any]", r["fixed"])
        for test in cast("list[str]", fixed.get("tests") or []):
            found.setdefault(test.partition("::")[0], cast("str", r["branch"]))
    return found


def left(
    fixes: list[dict[str, Any]], ratchets: list[dict[str, Any]], ended: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The fixes and ratchets still to plan, given the outcomes so far. An agent that didn't
    answer left no outcome. An accepted ratchet keeps its name, so its findings stay on its
    branch, but nothing to run; one that ended otherwise frees its findings."""
    states = {cast("str", r["key"]): state(r) for r in ended}
    again = taken_up(ended)
    moved = {key: files for key, files in again.items() if files}
    done = {key for key, s in states.items() if s != "failed"} - set(again)
    dropped = {key.removeprefix("ratchet:") for key in done if states[key] != "accepted"}
    fixes = [
        {**f, "ratchet": None} if f.get("ratchet") in dropped else f
        for f in fixes
        if f["key"] not in done
    ]
    fixes = [
        {**f, "verdict": {**f["verdict"], "test_files": moved[f["key"]]}}
        if f["key"] in moved
        else f
        for f in fixes
    ]
    ratchets = [
        {**r, "run": r["key"] not in done}
        for r in ratchets
        if r["key"] not in done or states[r["key"]] == "accepted"
    ]
    return fixes, ratchets


def main(run: Path) -> int:
    handed = _records(run / "fixes.jsonl")
    ended = _records(run / "outcomes.jsonl")
    fixes, ratchets = left(handed, _records(run / "ratchets.jsonl"), ended)
    planned = groups(fixes, ratchets, held(ended), lens_of(run))
    (run / "groups.json").write_text(json.dumps(planned, indent=2) + "\n", encoding="utf-8")
    unnamed = sum(1 for f in fixes if not _files(f))
    sizes = sorted((len(g["fixes"]) for g in planned), reverse=True)
    print(f"{len(fixes)} fixes on {len(planned)} branches, by size {sizes}: groups.json written")
    if len(handed) > len(fixes):
        print(f"{len(handed) - len(fixes)} fixes have an outcome and aren't planned again")
    for g in planned:
        if g["also"]:
            print(
                f"{g['branch']}: its files' earlier commits are also on "
                f"{', '.join(g['also'])}; merge those first",
                file=sys.stderr,
            )
    unaccepted = {str(r.get("branch")) for r in ended if state(r) in NOT_ACCEPTED}
    for branch in sorted(unaccepted & {cast("str", g["branch"]) for g in planned}):
        print(
            f"{branch} holds commits no review accepted (outcomes.json): "
            "drop them before the fix stage",
            file=sys.stderr,
        )
    if unnamed:
        print(f"{unnamed} fixes name no test file and stay with their survey", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
