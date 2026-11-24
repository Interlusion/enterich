"""The code lens's inventory (ADR-008): the code the lens surveys, in the records of
`harness/modules.jsonl`, the lens's fixed vocabulary, each with deterministic hints.

A record is a survey: a group of modules read for the concerns that show within them (lost
on the way, a wrong outcome after a side effect), or the whole code read for one concern
that shows only across modules (a rule written twice, a missed pattern). Every Python file
of the code is in exactly one group; a file in no group or in two, a path that doesn't
exist, a concern that isn't the lens's, or a record that doesn't say what it asks stops the
inventory: the vocabulary follows the code.

The hints point the surveys at places, they decide nothing: per group, the functions above
a stricter complexity than CI's, and the lines and branches the unit and integration tests
never run; for the whole code, the literals two modules share. With `--since <commit>`,
usually where the last run's records were committed, it also names the files changed since
then and the records they touch: a group with a changed file, and the surveys across the
code when any file of it changed. A run after the first surveys those. Read-only but for
the run directory; it runs the tests once, for their coverage.

    uv run python harness/modules.py harness/runs/<date>-code [--since <commit>]
"""

import argparse
import ast
import json
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, cast

try:
    from harness import engine, project, surface
    from harness.jsonl import read as _records
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import engine  # type: ignore[import-not-found, no-redef]
    import project  # type: ignore[import-not-found, no-redef]
    import surface  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]

ROOT = project.ROOT
MODULES = project.CHILD / "modules.jsonl"
CODE = project.SOURCES["code"]
# The lens's kinds of finding (harness/lenses/code.toml): within a group of modules, and across
_SCOPES = {name: concern["scope"] for name, concern in engine.kinds("code").items()}
LOCAL = tuple(name for name, scope in _SCOPES.items() if scope == "local")
ACROSS = tuple(name for name, scope in _SCOPES.items() if scope == "across")
CONCERNS = (*LOCAL, *ACROSS)

Records = list[dict[str, Any]]


def vocabulary() -> Records:
    return _records(MODULES)


def _files(record: dict[str, Any]) -> list[str]:
    return cast("list[str]", record.get("files") or [])


def _under(path: str, entry: str) -> bool:
    return path == entry or path.startswith(entry.rstrip("/") + "/")


def _across(record: dict[str, Any]) -> bool:
    return any(c in ACROSS for c in cast("list[str]", record.get("concerns") or []))


def code_files(root: Path = ROOT) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in (root / CODE).rglob("*.py"))


def unkept(records: Records, root: Path = ROOT) -> list[str]:
    """What is wrong with the vocabulary; empty when the inventory can be taken."""
    names = [str(r.get("promise")) for r in records]
    problems = [f"{n}: two records of this name" for n in sorted(set(names)) if names.count(n) > 1]
    for r in records:
        name = r.get("promise")
        problems += [f"{name}: {p} doesn't exist" for p in _files(r) if not (root / p).exists()]
        concerns = cast("list[str]", r.get("concerns") or [])
        if not concerns:
            problems.append(f"{name}: names no concern")
        problems += [f"{name}: {c} isn't the lens's" for c in concerns if c not in CONCERNS]
        if any(c in ACROSS for c in concerns) and any(c in LOCAL for c in concerns):
            problems.append(f"{name}: a concern across the code and one within a group")
        if not str(r.get("asks") or "").strip():
            problems.append(f"{name}: says nothing it asks")
    groups = [r for r in records if not _across(r)]
    for path in code_files(root):
        held = sum(1 for r in groups if any(_under(path, f) for f in _files(r)))
        if held != 1:
            problems.append(f"{path}: in {f'{held} groups' if held else 'no group'}")
    return problems


def touched(records: Records, files: list[str]) -> list[str]:
    """The records a change to the files touches: a group with a changed file of its own,
    and the surveys across the code when any file of it changed."""
    code = [f for f in files if _under(f, CODE) and f.endswith(".py")]
    return sorted(
        str(r["promise"])
        for r in records
        if (_across(r) and code) or any(_under(f, p) for f in code for p in _files(r))
    )


def _literal(node: ast.AST, length: int, size: int) -> str | None:
    """A literal worth comparing across modules: a long string or a large number."""
    if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
        return None
    value = node.value
    if isinstance(value, str) and len(value) >= length:
        return repr(value)
    if isinstance(value, int | float) and abs(value) >= size:
        return repr(value)
    return None


def _skipped(tree: ast.AST) -> set[int]:
    """The ids of the constants that hold no rule: docstrings, which say what a module or
    function is, the parts of an f-string, and the type a `cast` names."""
    found: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = cast("list[ast.stmt]", body)[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                found.add(id(first.value))
        if isinstance(node, ast.JoinedStr):
            found |= {id(v) for v in node.values}
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "cast" and node.args:
            found.add(id(node.args[0]))
    return found


def shared_literals(sources: dict[str, str], length: int, size: int) -> list[dict[str, Any]]:
    """Each literal that two or more modules hold, with where: a hint of a rule written
    twice."""
    places: dict[str, list[str]] = defaultdict(list)
    for path, text in sorted(sources.items()):
        tree = ast.parse(text)
        skip = _skipped(tree)
        for node in ast.walk(tree):
            if id(node) in skip:
                continue
            if (literal := _literal(node, length, size)) is not None:
                places[literal].append(f"{path}:{getattr(node, 'lineno', 0)}")
    return [
        {"literal": literal, "places": where}
        for literal, where in sorted(places.items())
        if len({w.rpartition(":")[0] for w in where}) > 1
    ]


def _spans(numbers: list[int]) -> str:
    """Line numbers as spans: 3-5, 9."""
    spans: list[str] = []
    for n in sorted(numbers):
        if spans and int(spans[-1].rpartition("-")[2]) == n - 1:
            spans[-1] = f"{spans[-1].partition('-')[0]}-{n}"
        else:
            spans.append(str(n))
    return ", ".join(spans)


def uncovered(report: dict[str, Any], files: list[str]) -> dict[str, str]:
    """Per file, the lines the tests never ran and the lines whose branches they never took
    both ways, from coverage's JSON report."""
    found: dict[str, str] = {}
    measured = cast("dict[str, dict[str, Any]]", report.get("files") or {})
    for path in files:
        data = measured.get(path)
        if data is None:
            continue
        lines = cast("list[int]", data.get("missing_lines") or [])
        branches = {int(b[0]) for b in cast("list[list[int]]", data.get("missing_branches") or [])}
        if lines or branches:
            text = _spans(lines)
            if branches - set(lines):
                text += f"{'; ' if text else ''}branches at {_spans(sorted(branches - set(lines)))}"
            found[path] = text
    return found


def complex_functions(diagnostics: list[dict[str, Any]], files: list[str]) -> list[str]:
    """The functions ruff names above the lens's complexity, as `path:line message`."""
    found: list[str] = []
    for d in diagnostics:
        path = Path(str(d.get("filename"))).resolve()
        try:
            name = path.relative_to(ROOT).as_posix()
        except ValueError:
            name = path.as_posix()
        if name in files:
            row = cast("dict[str, Any]", d.get("location") or {}).get("row")
            found.append(f"{name}:{row} {d.get('message')}")
    return sorted(found)


def _ruff(files: list[str], root: Path) -> list[dict[str, Any]]:
    limit = int(project.CODE["complexity"])
    run = subprocess.run(  # noqa: S603 - fixed arguments, the repository's own files
        [  # noqa: S607 - uv from PATH, as every script here
            "uv", "run", "ruff", "check", "--select", "C901", "--output-format", "json",
            "--config", f"lint.mccabe.max-complexity={limit}", *files,
        ],
        cwd=root, capture_output=True, text=True, check=False,
    )  # fmt: skip
    return cast("list[dict[str, Any]]", json.loads(run.stdout or "[]"))


def _coverage(root: Path) -> dict[str, Any]:
    """The unit and integration tests' coverage, as CI measures it; kept out of the run,
    whose records take only the hints."""
    tests = [project.SOURCES["tests"] + d for d in ("/unit", "/integration")]
    with tempfile.TemporaryDirectory() as scratch:
        report = Path(scratch) / "coverage.json"
        data = Path(scratch) / ".coverage"
        for command in (
            ["uv", "run", "coverage", "run", f"--data-file={data}", "-m", "pytest", "-q",
             "-p", "no:cacheprovider", *tests],
            ["uv", "run", "coverage", "json", f"--data-file={data}", "-o", str(report)],
        ):  # fmt: skip
            subprocess.run(command, cwd=root, capture_output=True, check=True)  # noqa: S603
        return cast("dict[str, Any]", json.loads(report.read_text(encoding="utf-8")))


def hints(records: Records, root: Path, coverage: dict[str, Any]) -> Records:
    """Each record with its hints: a group's complex functions and untested lines, the
    surveys across the code the literals two modules share."""
    files = code_files(root)
    sources = {f: (root / f).read_text(encoding="utf-8") for f in files}
    shared = shared_literals(
        sources, int(project.CODE["literal_length"]), int(project.CODE["number_size"])
    )
    complex_ = complex_functions(_ruff(files, root), files)
    out: Records = []
    for r in records:
        if _across(r):
            out.append({**r, "hints": {"shared_literals": shared}})
            continue
        own = [f for f in files if any(_under(f, p) for p in _files(r))]
        out.append(
            {
                **r,
                "hints": {
                    "complex": [c for c in complex_ if c.partition(":")[0] in own],
                    "untested": uncovered(coverage, own),
                },
            }
        )
    return out


def main(run: Path, root: Path = ROOT, since: str | None = None) -> int:
    records = vocabulary()
    problems = unkept(records, root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    run.mkdir(parents=True, exist_ok=True)
    surveyed = hints(records, root, _coverage(root))
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in surveyed)
    (run / "modules.jsonl").write_text(text, encoding="utf-8")
    counts: dict[str, int] = {"records": len(surveyed)}
    if since is not None:
        files = surface.changed(since, root)
        hit = touched(records, files)
        commit = surface._git(root, "rev-parse", since).strip()  # pyright: ignore[reportPrivateUsage]
        written = {"commit": commit, "changed": files, "records": hit}
        (run / "since.json").write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
        counts |= {"changed": len(files), "touched": len(hit)}
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", type=Path, help="the run directory")
    parser.add_argument("--since", help="survey what changed after this commit")
    a = parser.parse_args()
    sys.exit(main(a.run, since=a.since))
