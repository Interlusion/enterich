"""The tests lens's inventory (ADR-008): the specs' requirements with their Definition of
Done items, the tests with the requirement IDs they cite, and both directions of the
trace. Deterministic and read-only; writes JSON Lines to the run directory given.

    uv run python harness/inventory.py harness/runs/<date>-tests
"""

import ast
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from harness import project
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import project  # type: ignore[import-not-found, no-redef]

ROOT = project.ROOT
SPECS = ROOT / project.SOURCES["specs"]
TESTS = ROOT / project.SOURCES["tests"]
# Tests that cite requirement IDs as data, not as what they check
LEFT_OUT = {
    p for glob in project.strings(project.SOURCES, "tests_left_out") for p in ROOT.glob(glob)
}
ID = re.compile(project.SOURCES["requirement_id"])
HEADING = re.compile(rf"^#### ({ID.pattern}): (.+)$")
CLOSING = project.strings(project.SOURCES, "dod_closing")


@dataclass
class Requirement:
    id: str
    spec: str
    title: str
    dod: list[str] = field(default_factory=list[str])
    # Tests citing the ID in their own code, and those under a section or module citing it
    tests: list[str] = field(default_factory=list[str])
    tests_by_section: list[str] = field(default_factory=list[str])


@dataclass
class Test:
    id: str
    ids: list[str]
    section_ids: list[str]


def requirements() -> list[Requirement]:
    found: list[Requirement] = []
    for spec in sorted(SPECS.glob(project.SOURCES["spec_glob"])):
        if spec.name.endswith(".history.md"):
            continue
        current: Requirement | None = None
        in_dod = False
        for line in spec.read_text(encoding="utf-8").splitlines():
            if heading := HEADING.match(line):
                current = Requirement(heading[1], spec.name, heading[2])
                found.append(current)
                in_dod = False
            elif line.startswith("#"):
                current, in_dod = None, False
            elif current and line.startswith("**Definition of Done**"):
                in_dod = True
            elif current and in_dod and line.startswith("- ") and not line.startswith(CLOSING):
                current.dod.append(line[2:])
            elif in_dod and line.startswith("**"):
                in_dod = False
    return found


def section_ids(lines: list[str], before: int) -> list[str]:
    """The IDs of the section line `before` (1-based) is in: of every line of the nearest
    top-level comment block above it that stands on its own, a blank line after it. A
    comment on the line below it is about that line, no heading; a heading citing nothing
    starts a section citing nothing."""
    at = before - 2
    while at >= 0:
        if not lines[at].startswith("#"):
            at -= 1
            continue
        start = at
        while start > 0 and lines[start - 1].startswith("#"):
            start -= 1
        after = lines[at + 1] if at + 1 < len(lines) else ""
        if not after.strip():
            return sorted({i for line in lines[start : at + 1] for i in ID.findall(line)})
        at = start - 1
    return []


def tests() -> list[Test]:
    found: list[Test] = []
    for path in sorted(set(TESTS.rglob("test_*.py")) - LEFT_OUT):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        lines = source.splitlines()
        module_ids = set(ID.findall(ast.get_docstring(tree) or ""))
        nodes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)]
        for cls in nodes:
            functions += [
                n for n in cls.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
        for node in functions:
            if not node.name.startswith("test_"):
                continue
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            own = "\n".join(lines[start - 1 : node.end_lineno])
            section = set(section_ids(lines, start)) | module_ids
            found.append(
                Test(
                    f"{path.relative_to(ROOT)}::{node.name}",
                    sorted(set(ID.findall(own))),
                    sorted(section),
                )
            )
    return found


def main(run: Path) -> None:
    reqs, cases = requirements(), tests()
    by_id = {r.id: r for r in reqs}
    for case in cases:
        for rid in case.ids:
            if rid in by_id:
                by_id[rid].tests.append(case.id)
        for rid in case.section_ids:
            if rid in by_id and case.id not in by_id[rid].tests:
                by_id[rid].tests_by_section.append(case.id)
    run.mkdir(parents=True, exist_ok=True)
    unknown = sorted({i for c in cases for i in (*c.ids, *c.section_ids)} - set(by_id))
    with (run / "requirements.jsonl").open("w", encoding="utf-8") as out:
        out.writelines(json.dumps(asdict(r), ensure_ascii=False) + "\n" for r in reqs)
    with (run / "tests.jsonl").open("w", encoding="utf-8") as out:
        out.writelines(json.dumps(asdict(c), ensure_ascii=False) + "\n" for c in cases)
    prs = [r for r in reqs if "-PRS-" in r.id]
    summary = {
        "requirements": len(reqs),
        "prs": len(prs),
        "dod_items": sum(len(r.dod) for r in prs),
        "prs_without_any_test": [r.id for r in prs if not r.tests and not r.tests_by_section],
        "prs_only_by_section": [r.id for r in prs if not r.tests and r.tests_by_section],
        "tests": len(cases),
        "tests_without_any_id": sum(1 for c in cases if not c.ids and not c.section_ids),
        "ids_cited_but_not_in_a_spec": unknown,
    }
    (run / "inventory.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in summary.items()}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
