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

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "docs" / "specs"
TESTS = ROOT / "tests"
# Requirement IDs in full, as the specs index writes them
ID = re.compile(r"REQ-\d{3}-(?:URS|PRS)-N?F\d{3}")
HEADING = re.compile(r"^#### (REQ-\d{3}-(?:URS|PRS)-N?F\d{3}): (.+)$")
# The DoD's closing lines say how it is verified, not what
CLOSING = ("- Verification:", "- Evidence:")


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
    for spec in sorted(SPECS.glob("req-*.md")):
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


def _section_ids(lines: list[str], before: int) -> list[str]:
    """The IDs of the last top-level comment line citing any above line `before` (1-based)."""
    for line in reversed(lines[: before - 1]):
        if line.startswith("# ") and ID.search(line):
            return sorted(set(ID.findall(line)))
    return []


def tests() -> list[Test]:
    found: list[Test] = []
    for path in sorted(TESTS.rglob("test_*.py")):
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
            section = set(_section_ids(lines, start)) | module_ids
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
