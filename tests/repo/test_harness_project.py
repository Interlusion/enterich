"""The improvement pipeline's values for this repository are in one place,
`harness/project.toml` (analysis 003, section 3.6): the scripts take them from there and name
none of them themselves, so the file becomes a child skill's hooks as it is. A value of the
wrong form stops the scripts instead of making a check read nothing."""

import ast
import copy
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

from harness import documents, gate, inventory, project, surface, sweep, triage

VALUES: dict[str, Any] = tomllib.loads(project.FILE.read_text(encoding="utf-8"))
SOURCES, SECURITY, GATE = VALUES["sources"], VALUES["security"], VALUES["gate"]
# The method's own place, and the lenses' names, are no values of the repository's
METHOD = {"harness/", ".claude/"}
LENSES = set(triage.LENSES)


def test_the_scripts_take_the_projects_values() -> None:
    root = project.ROOT
    assert SOURCES["requirement_id"] == inventory.ID.pattern
    assert inventory.HEADING.match("#### REQ-001-PRS-F001: Title")
    assert root / SOURCES["specs"] == inventory.SPECS
    assert root / SOURCES["tests"] == inventory.TESTS
    assert tuple(SOURCES["dod_closing"]) == inventory.CLOSING
    assert {p.name for p in inventory.LEFT_OUT} >= {"test_harness.py", Path(__file__).name}
    assert triage.MUTANT.match(f"{SOURCES['package']}.shapes.x_page__mutmut_9")
    assert root / SOURCES["backlog"] == triage.BACKLOG
    assert root / SOURCES["code"] == sweep.SRC
    assert sweep.location(f"{SOURCES['package']}.auth.x_f__mutmut_1").startswith(SOURCES["code"])
    assert Path(SOURCES["code"]) == surface.SRC
    assert SECURITY["policy"] == surface.POLICY
    assert Path(SECURITY["tool_snapshot"]) == surface.TOOLS
    assert tuple(VALUES["docs"]["scope"]) == documents.SCOPE
    assert (GATE["base"], GATE["remote"]) == (gate.BASE, gate.REMOTE)
    assert f"{SOURCES['tests']}/" == gate.TESTS
    assert (gate.TESTS, f"{SOURCES['code']}/", *GATE["allowed_besides"]) == gate.ALLOWED
    assert tuple(GATE["forbidden"]) == gate.FORBIDDEN
    assert tuple(GATE["forbidden_names"]) == gate.FORBIDDEN_NAMES
    assert GATE["checks"] == gate.CHECKS
    assert GATE["scanner_image"] == gate.SCANNER_IMAGE
    assert gate.COMMIT.match("fix(gate): a")
    assert not gate.COMMIT.match("style: a")


def test_one_fact_in_one_place() -> None:
    """What the file holds twice, or another file holds too, is held equal."""
    mutmut = tomllib.loads((project.ROOT / "pyproject.toml").read_text())["tool"]["mutmut"]
    assert [f"{SOURCES['code']}/"] == mutmut["paths_to_mutate"]
    assert Path(SOURCES["code"]).name == SOURCES["package"]
    # The contract and the tool list change only by the operator's hand (ADR-008)
    assert f"{SOURCES['specs']}/" in GATE["forbidden"]
    assert f"{Path(SECURITY['tool_snapshot']).parent}/" in GATE["forbidden"]


def _wrong(section: str, key: str, value: object) -> list[str]:
    values = copy.deepcopy(VALUES)
    values[section][key] = value
    return project.problems(values)


def test_the_repositorys_values_have_their_form() -> None:
    assert project.problems(VALUES) == []


@pytest.mark.parametrize(
    ("section", "key", "value", "problem"),
    [
        # A string where a list belongs would be read as its letters
        ("gate", "forbidden_names", "ruff.toml", "gate.forbidden_names: a list of strings"),
        ("sources", "dod_closing", "- Verification:", "sources.dod_closing: a list"),
        ("sources", "tests", "tests/", "sources.tests: a directory without a trailing slash"),
        ("sources", "requirement_id", r"REQ-(URS|PRS)", "sources.requirement_id: no capturing"),
        ("sources", "requirement_id", "REQ-(", "sources.requirement_id: not a regular"),
        ("gate", "commit_types", ["feat", "fix", "test"], "gate.commit_types: without refactor"),
        # The check whose results the gate compares with main's
        ("gate", "checks", {"unit": ["uv", "run", "pytest"]}, "gate.checks: no tests"),
        ("gate", "checks", {"tests": "uv run pytest"}, "gate.checks.tests: a list of strings"),
    ],
)
def test_a_value_of_the_wrong_form_is_refused(
    section: str, key: str, value: object, problem: str
) -> None:
    assert any(p.startswith(problem) for p in _wrong(section, key, value))


def _named() -> list[str]:
    """The values no script should spell out: each in full, as it stands in the file."""
    return sorted(
        {
            *(SOURCES[k] for k in ("specs", "code", "backlog")),
            f"{SOURCES['tests']}/",
            SECURITY["policy"],
            SECURITY["tool_snapshot"],
            GATE["base"],
            GATE["scanner_image"],
            GATE["scanner_image_dir"],
            *GATE["allowed_besides"],
            *(p for p in GATE["forbidden"] if p not in METHOD),
            *GATE["forbidden_names"],
        }
    )


def _segments() -> set[str]:
    """The parts of the file's paths that a script could join (`ROOT / "docs" / "specs"`)."""
    paths = [SOURCES[k] for k in ("specs", "code", "backlog")] + [SECURITY["tool_snapshot"]]
    return {part for path in paths for part in Path(path).parts} - LENSES


def offending(source: str) -> list[tuple[int, str]]:
    """The string literals of a script, its docstrings left out, that spell out a value of
    the file: in full, as one part of one of its paths, or the package as a word."""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    # A key read from a mapping (`project.SOURCES["specs"]`, `record.get("backlog")`) is a
    # name, not a value
    keys = {
        id(key)
        for node in ast.walk(tree)
        for key in (
            [node.slice]
            if isinstance(node, ast.Subscript)
            else node.args[:1]
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            else []
        )
    }
    named, segments = _named(), _segments()
    package = re.compile(rf"(?<![\w-]){re.escape(SOURCES['package'])}(?![\w-])")
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings | keys
        and (
            any(value in node.value for value in named)
            or node.value in segments
            or package.search(node.value)
        )
    ]


def test_the_spellings_main_had_are_found() -> None:
    """main's own spellings before the file, each found."""
    planted = (
        'SPECS = ROOT / "docs" / "specs"\n'
        'SRC = Path("src") / "enterich"\n'
        'TOOLS = Path("tests") / "snapshots" / "tools.json"\n'
        'MUTANT = re.compile(r"^enterich\\.[\\w.]+__mutmut_\\d+$")\n'
        'TEST_FILE = re.compile(r"\\btests/[\\w/]+\\.py\\b")\n'
        'POLICY = "SECURITY.md"\n'
        'NAMES = ("ruff.toml", "pytest.ini")\n'
        'BACKLOG = ROOT / "docs" / "backlog"\n'
    )
    assert sorted({line for line, _ in offending(planted)}) == list(range(1, 9))


def test_a_lens_a_key_or_a_word_that_isnt_a_value_passes() -> None:
    text = (
        'L = {"tests": 1, "docs": 2}\nN = "enterich_like"\nS = SOURCES["specs"]\nr.get("backlog")\n'
    )
    assert offending(text) == []


@pytest.mark.parametrize(
    "script",
    sorted(p for p in (project.ROOT / "harness").glob("*.py") if p.name != "project.py"),
    ids=lambda p: p.name,
)
def test_no_script_names_a_value_of_the_project_file(script: Path) -> None:
    found = offending(script.read_text(encoding="utf-8"))
    assert [f"{script.name}:{line}: {text!r}" for line, text in found] == []


# The workflows' prompts take what they say about the repository from the brief

WORKFLOWS = sorted((project.ROOT / ".claude" / "workflows").glob("*.js"))


def _code(script: Path) -> str:
    """A workflow without its comment lines."""
    lines = script.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("//"))


def test_the_brief_is_what_the_workflows_read() -> None:
    """Every phrase a prompt asks for is in the brief, and every phrase of it is asked for."""
    used = {name for s in WORKFLOWS for name in re.findall(r"\bB\.(\w+)", _code(s))}
    assert sorted(used) == sorted(project.brief())


@pytest.mark.parametrize("script", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_names_what_the_brief_says(script: Path) -> None:
    """A phrase of the brief written into a prompt would stay when the brief changes."""
    code = _code(script)
    found = [
        f"{key}: {value!r}"
        for key, value in project.brief().items()
        if len(value) > 3 and re.search(rf"(?<![\w-]){re.escape(value)}(?![\w-])", code)
    ]
    assert found == []
    assert "const B = args.brief" in code


def test_the_brief_is_printed_for_the_session() -> None:
    printed = subprocess.run(
        [sys.executable, "harness/project.py", "brief"],
        cwd=project.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert json.loads(printed) == project.brief()
