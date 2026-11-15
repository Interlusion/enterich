"""The tests lens's mutation step (ADR-008): runs mutmut over `src/enterich/` against the
unit and integration tests (`[tool.mutmut]` in pyproject.toml), then writes each surviving
mutant with its diff, and the counts per module, to the run directory given. CPU only;
mutmut keeps its results in `mutants/`, so a second run checks only what changed.

A survivor a script can judge gets a `filter` and isn't surveyed. What a string is follows
from where it goes, read from the function's source, not from what it looks like: only the
wording of an error that is raised or of a log message is noise. A string that goes
anywhere else (a name, a format, a header, a result's text) is left to the agents.

    uv run --group harness python harness/mutation.py harness/runs/<date>-tests [--fresh]
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    from harness.sweep import location
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    from sweep import location  # type: ignore[import-not-found, no-redef]

ROOT = Path(__file__).resolve().parent.parent
MUTMUT = [sys.executable, "-m", "mutmut"]
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
CAST = re.compile(r'(?<![\w.])cast\("[^"]*",')
LEVELS = {"debug", "info", "warning", "error", "exception", "critical"}


def _is_message(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> bool:
    """Whether a string is the wording of a raised error or of a log message: an argument
    of the call that is raised, or a logger's first, itself or joined with others."""
    child, parent = node, parents[node]
    while isinstance(parent, ast.BinOp | ast.JoinedStr) or (
        isinstance(parent, ast.IfExp) and child is not parent.test
    ):
        child, parent = parent, parents[parent]
    if not (isinstance(parent, ast.Call) and child in parent.args):
        return False
    raised = parents.get(parent)
    if isinstance(raised, ast.Raise) and raised.exc is parent:
        return True
    func = parent.func
    if not (isinstance(func, ast.Attribute) and func.attr in LEVELS and parent.args[0] is child):
        return False
    owner = func.value
    name = owner.id if isinstance(owner, ast.Name) else getattr(owner, "attr", "")
    return "log" in str(name).lower()


def message_lines(source: str, function: str) -> dict[str, bool]:
    """The lines of a function (`name` or `Class.method`) that hold a string, each without
    its indentation, with whether every string on it is a message's wording. A line that
    reads the same in two places counts by both."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    *owner, name = function.split(".")

    def named(node: ast.AST) -> bool:
        if not (isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == name):
            return False
        holder = parents.get(node)
        return not owner or (isinstance(holder, ast.ClassDef) and holder.name == owner[0])

    lines = source.splitlines()
    found: dict[str, bool] = {}
    for function_node in (n for n in ast.walk(tree) if named(n)):
        for node in ast.walk(function_node):
            parent = parents[node]
            if not isinstance(node, ast.Constant | ast.JoinedStr):
                continue
            if isinstance(node, ast.Constant) and not isinstance(node.value, str):
                continue
            # A part of an f-string counts with it; a format after the colon is no string
            if isinstance(parent, ast.JoinedStr):
                continue
            if isinstance(parent, ast.FormattedValue) and parent.format_spec is node:
                continue
            message = _is_message(node, parents)
            first, last = node.lineno, node.end_lineno or node.lineno
            for line in lines[first - 1 : last]:
                found[line.strip()] = found.get(line.strip(), True) and message
    return found


def filtered(diff: str, messages: Mapping[str, bool] | None = None) -> str | None:
    """Why a script can judge a survivor without an agent: "message" when only the text of
    strings with a space changed, on lines whose strings are all a message's wording
    (`messages`, from the function's source; none without it), "cast" when only the type
    text of a `cast()` did; None when it needs an agent."""
    removed = [line[1:] for line in diff.splitlines() if line.startswith("-")]
    added = [line[1:] for line in diff.splitlines() if line.startswith("+")]
    if not removed or len(removed) != len(added):
        return None
    if all(
        CAST.sub("cast(T,", a) == CAST.sub("cast(T,", b)
        for a, b in zip(removed, added, strict=True)
    ):
        return "cast"
    for before, after in zip(removed, added, strict=True):
        if STRING.sub('""', before) != STRING.sub('""', after):
            return None
        changed = [
            old
            for old, new in zip(STRING.findall(before), STRING.findall(after), strict=False)
            if old != new
        ]
        if not changed or not all(" " in old for old in changed):
            return None
        if not (messages or {}).get(before.strip(), False):
            return None
    return "message"


def messages_of(mutant: str, root: Path = ROOT) -> dict[str, bool]:
    """A mutant's function's lines with a string, by `message_lines`; none if the source
    can't be read."""
    file, _, function = location(mutant).partition(":")
    try:
        return message_lines((root / file).read_text(encoding="utf-8"), function)
    except OSError, SyntaxError:
        return {}


def _mutmut(*args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [*MUTMUT, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"mutmut {' '.join(args)} failed: {done.stderr[-2000:]}")
    return done.stdout


def _diff(mutant: str) -> str:
    shown = _mutmut("show", mutant)
    return "\n".join(
        line
        for line in shown.splitlines()
        if line.startswith(("-", "+")) and not line.startswith(("---", "+++"))
    )


def _module(mutant: str) -> str:
    """`enterich.shapes.x_page__mutmut_3` → `enterich.shapes`."""
    head = mutant.split("__mutmut_")[0]
    return ".".join(p for p in head.split(".") if not p.startswith(("x_", "xǁ")))


def main(run: Path, fresh: bool) -> None:
    if fresh:
        shutil.rmtree(ROOT / "mutants", ignore_errors=True)
    workers = str(os.cpu_count() or 2)
    subprocess.run([*MUTMUT, "run", "--max-children", workers], cwd=ROOT, check=True)  # noqa: S603
    statuses: dict[str, str] = {}
    for line in _mutmut("results", "--all", "true").splitlines():
        name, _, status = line.strip().rpartition(": ")
        if name:
            statuses[name] = status
    survivors = sorted(n for n, s in statuses.items() if s == "survived")
    with ThreadPoolExecutor(max_workers=int(workers)) as pool:
        diffs = list(pool.map(_diff, survivors))
    run.mkdir(parents=True, exist_ok=True)
    filters = [
        filtered(diff, messages_of(name)) for name, diff in zip(survivors, diffs, strict=True)
    ]
    with (run / "survivors.jsonl").open("w", encoding="utf-8") as out:
        for name, diff, judged in zip(survivors, diffs, filters, strict=True):
            record = {"id": name, "module": _module(name), "filter": judged, "diff": diff}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    per_module: dict[str, Counter[str]] = {}
    for name, status in statuses.items():
        per_module.setdefault(_module(name), Counter())[status] += 1
    summary = {
        "mutants": len(statuses),
        "by_status": dict(Counter(statuses.values())),
        "survivors_filtered": dict(Counter(f for f in filters if f)),
        "by_module": {m: dict(c) for m, c in sorted(per_module.items())},
    }
    (run / "mutation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("mutants", "by_status")}, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--fresh" in sys.argv[2:])
