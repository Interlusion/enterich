"""The security lens's inventory (ADR-008): the promises the lens checks, each with its
requirements and the tests citing them, and the surface they are kept on: the tools with
their text inputs without a bound, every request Enterich sends ERPNext and where the tools
make it, every log call, the settings, and every silenced security rule of the linter.

The promises are the lens's fixed vocabulary, `harness/promises.jsonl`: what `SECURITY.md`
names as in scope and the rules of `AGENTS.md` about what Enterich may do, each by a text
of its source. A promise whose text its source no longer holds, or a line of the security
policy's scope without a promise, stops the inventory: the vocabulary follows the policy.
With `--since <commit>`, usually where the last run's records were committed, it also names
the files changed since then and the promises they touch: a change to a promise's source or
under one of its start paths. A run after the first surveys those promises, on those
changes. Deterministic and read-only; writes to the run directory given.

    uv run python harness/surface.py harness/runs/<date>-security [--since <commit>]
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

try:
    from harness import inventory, project
    from harness.jsonl import read as _records
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import inventory  # type: ignore[import-not-found, no-redef]
    import project  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]

ROOT = project.ROOT
PROMISES = project.CHILD / "promises.jsonl"
POLICY = project.SECURITY["policy"]
SRC = Path(project.SOURCES["code"])
TOOLS = Path(project.SECURITY["tool_snapshot"])
# What bounds a text input: a length, a fixed set, or a form
BOUNDS = ("maxLength", "enum", "const", "format", "pattern")
NOQA = re.compile(r"#\s*noqa:[^#\n]*\bS\d{3}")

Records = list[dict[str, Any]]


def scope(policy: str) -> list[str]:
    """The security policy's lines of what is in scope: each bullet between its Scope
    heading and "Out of scope", but one that only heads the bullets below it."""
    lines = policy.split("\n## Scope\n", 1)[-1].split("\nOut of scope", 1)[0].splitlines()
    bullets = [line.strip()[2:] for line in lines if line.strip().startswith("- ")]
    return [b for b in bullets if not re.fullmatch(r"\*\*[^*]+:\*\*", b)]


def unkept(promises: Records, root: Path = ROOT) -> list[str]:
    """What is wrong with the vocabulary; empty when the inventory can be taken."""
    problems: list[str] = []
    names = [str(p.get("promise")) for p in promises]
    problems += [
        f"{n}: two promises of this name" for n in sorted(set(names)) if names.count(n) > 1
    ]
    sources: dict[str, str] = {}
    for p in promises:
        source = str(p.get("source"))
        if source not in sources:
            path = root / source
            sources[source] = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not p.get("text") or str(p["text"]) not in sources[source]:
            problems.append(f"{p.get('promise')}: {source} doesn't hold its text")
        problems += [
            f"{p.get('promise')}: {start} doesn't exist"
            for start in cast("list[str]", p.get("start") or [])
            if not (root / start).exists()
        ]
    policy = root / POLICY
    texts = [str(p.get("text")) for p in promises if p.get("source") == POLICY]
    for line in scope(policy.read_text(encoding="utf-8") if policy.is_file() else ""):
        held = sum(1 for t in texts if t in line)
        if held != 1:
            problems.append(f"{POLICY}: {held} promises for the line: {line[:60]}")
    return problems


def _resolved(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    return cast("dict[str, Any]", defs[ref.rsplit("/", 1)[-1]]) if isinstance(ref, str) else schema


def unbounded(
    schema: dict[str, Any], defs: dict[str, Any] | None = None, at: str = ""
) -> list[str]:
    """The inputs of a tool's schema that take a text of any length and form, each by its
    path: `accounts[].debit`."""
    defs = cast("dict[str, Any]", schema.get("$defs") or {}) if defs is None else defs
    schema = _resolved(schema, defs)
    found: list[str] = []
    if schema.get("type") == "string" and not any(b in schema for b in BOUNDS):
        found.append(at)
    for option in cast("list[dict[str, Any]]", schema.get("anyOf") or []):
        found += unbounded(option, defs, at)
    for name, part in cast("dict[str, dict[str, Any]]", schema.get("properties") or {}).items():
        found += unbounded(part, defs, f"{at}.{name}" if at else name)
    if isinstance(items := schema.get("items"), dict):
        found += unbounded(cast("dict[str, Any]", items), defs, f"{at}[]")
    return sorted(set(found))


def tools(root: Path = ROOT) -> Records:
    """The published tools, as the snapshot holds them: whether one writes, and its text
    inputs without a bound."""
    published = cast("Records", json.loads((root / TOOLS).read_text(encoding="utf-8")))
    return [
        {
            "tool": t["name"],
            "writes": not t["annotations"]["readOnlyHint"],
            "unbounded": unbounded(t["inputSchema"]),
        }
        for t in published
    ]


def _sources(root: Path) -> list[tuple[str, str, ast.Module]]:
    found: list[tuple[str, str, ast.Module]] = []
    for path in sorted((root / SRC).rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        found.append((path.relative_to(root).as_posix(), text, ast.parse(text)))
    return found


def _within(tree: ast.Module) -> dict[ast.AST, str]:
    """Each node's innermost function or class, by name."""
    inside: dict[ast.AST, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for child in ast.walk(node):
                if child is not node:
                    inside[child] = node.name
    return inside


def requests(root: Path = ROOT) -> Records:
    """Every request Enterich sends ERPNext: the client's calls of its one sender, each
    with the client's method it is in, the HTTP method and the path as written."""
    found: Records = []
    for file, _, tree in _sources(root):
        if not file.endswith("/erpnext.py"):
            continue
        inside = _within(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_call"
                and len(node.args) >= 2
            ):
                found.append(
                    {
                        "at": f"{file}:{node.lineno}",
                        "in": inside.get(node),
                        "method": ast.unparse(node.args[0]),
                        "path": ast.unparse(node.args[1]),
                    }
                )
    return sorted(found, key=lambda r: int(r["at"].rsplit(":", 1)[1]))


def client_calls(root: Path = ROOT) -> Records:
    """Where the code calls the ERPNext client (`….erpnext.<method>(…)`), with the first
    argument as written: the DocType or report a call is for."""
    client = ast.parse((root / SRC / "erpnext.py").read_text(encoding="utf-8"))
    methods = {
        line.name
        for node in client.body
        if isinstance(node, ast.ClassDef) and node.name == "Erpnext"
        for line in node.body
        if isinstance(line, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    found: Records = []
    for file, _, tree in _sources(root):
        inside = _within(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            owner = node.func.value
            name = owner.attr if isinstance(owner, ast.Attribute) else None
            name = owner.id if isinstance(owner, ast.Name) else name
            if name != "erpnext" or node.func.attr not in methods:
                continue
            found.append(
                {
                    "at": f"{file}:{node.lineno}",
                    "in": inside.get(node),
                    "call": node.func.attr,
                    "first": ast.unparse(node.args[0]) if node.args else None,
                }
            )
    return sorted(found, key=lambda r: (r["at"].rsplit(":", 1)[0], int(r["at"].rsplit(":", 1)[1])))


def log_calls(root: Path = ROOT) -> Records:
    """Every call of the log's `event` and `failure`, with the event's name and the fields
    given by name; `**` stands for fields put together elsewhere."""
    found: Records = []
    for file, _, tree in _sources(root):
        inside = _within(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            name = func.id if isinstance(func, ast.Name) else name
            owned = isinstance(func, ast.Attribute) and ast.unparse(func.value) == "log"
            if name not in {"event", "failure"} or not (owned or file.endswith("/log.py")):
                continue
            first = node.args[0] if node.args else None
            found.append(
                {
                    "at": f"{file}:{node.lineno}",
                    "in": inside.get(node),
                    "call": name,
                    "event": first.value if isinstance(first, ast.Constant) else None,
                    "fields": [k.arg or "**" for k in node.keywords],
                }
            )
    return sorted(found, key=lambda r: (r["at"].rsplit(":", 1)[0], int(r["at"].rsplit(":", 1)[1])))


def settings(root: Path = ROOT) -> Records:
    """The fields of the configuration's `Settings`, each with its type as written."""
    tree = ast.parse((root / SRC / "config.py").read_text(encoding="utf-8"))
    return [
        {"setting": line.target.id, "type": ast.unparse(line.annotation)}
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Settings"
        for line in node.body
        if isinstance(line, ast.AnnAssign) and isinstance(line.target, ast.Name)
    ]


def silenced(root: Path = ROOT) -> Records:
    """Every line of the code that silences a security rule of the linter, as written."""
    return [
        {"at": f"{file}:{number}", "line": line.strip()}
        for file, text, _ in _sources(root)
        for number, line in enumerate(text.splitlines(), 1)
        if NOQA.search(line)
    ]


def _git(root: Path, *args: str) -> str:
    return subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *args],  # noqa: S607
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def changed(since: str, root: Path = ROOT) -> list[str]:
    """The files changed between the commit and HEAD, from the repository root."""
    return sorted(_git(root, "diff", "--name-only", since, "HEAD").splitlines())


def touched(promises: Records, files: list[str]) -> list[str]:
    """The promises a change to the files touches: one to its source, or under a start."""

    def under(path: str, start: str) -> bool:
        return path == start or path.startswith(start.rstrip("/") + "/")

    return sorted(
        str(p["promise"])
        for p in promises
        if any(
            f == p.get("source")
            or any(under(f, s) for s in cast("list[str]", p.get("start") or []))
            for f in files
        )
    )


def traced(promises: Records) -> Records:
    """Each promise with its requirements as the tests lens's inventory reads them: the
    Definition of Done and the tests citing each."""
    by_id = {r.id: r for r in inventory.requirements()}
    for case in inventory.tests():
        for rid in case.ids:
            if rid in by_id:
                by_id[rid].tests.append(case.id)
        for rid in case.section_ids:
            if rid in by_id and case.id not in by_id[rid].tests:
                by_id[rid].tests_by_section.append(case.id)
    return [
        {**p, "requirements": [asdict(by_id[rid]) for rid in p["requirements"]]} for p in promises
    ]


def main(run: Path, root: Path = ROOT, since: str | None = None) -> int:
    promises = _records(PROMISES)
    known = {r.id for r in inventory.requirements()}
    problems = unkept(promises, root)
    problems += [
        f"{p.get('promise')}: {rid} is in no spec"
        for p in promises
        for rid in cast("list[str]", p.get("requirements") or [])
        if rid not in known
    ]
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    surface = {
        "tools": tools(root),
        "requests": requests(root),
        "client_calls": client_calls(root),
        "log_calls": log_calls(root),
        "settings": settings(root),
        "silenced": silenced(root),
    }
    counts: dict[str, int] = {"promises": len(promises)}
    counts |= {k: len(v) for k, v in surface.items()}
    counts["unbounded_inputs"] = sum(len(t["unbounded"]) for t in surface["tools"])
    written: dict[str, Any] = dict(surface)
    if since is not None:
        files = changed(since, root)
        hit = touched(promises, files)
        commit = _git(root, "rev-parse", since).strip()
        written["since"] = {"commit": commit, "changed": files, "promises": hit}
        counts |= {"changed": len(files), "touched": len(hit)}
    run.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in traced(promises))
    (run / "promises.jsonl").write_text(text, encoding="utf-8")
    (run / "surface.json").write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
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
