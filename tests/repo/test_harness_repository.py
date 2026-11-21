"""The pipeline's scripts work on the repository they are run from, the working directory,
and on its child, the repository's own files for the pipeline in `harness/` there; what
belongs to the method, the engine's definitions, they find beside themselves. Nothing finds
the repository from where the scripts lie, so they work from the skill's directory as they
work here (analysis 004, section 3.1, step 2)."""

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from harness import project

HARNESS = project.ROOT / "harness"
RUNS = HARNESS / "runs"
SCRIPTS = sorted(p for p in HARNESS.glob("*.py") if p.name != "__init__.py")
WORKFLOWS = sorted((project.ROOT / ".claude" / "workflows").glob("*.js"))


def test_the_repository_is_the_working_directory_and_its_child_is_harness() -> None:
    assert Path.cwd().resolve() == project.ROOT
    assert project.CHILD == project.ROOT / "harness"
    assert project.FILE == project.CHILD / "project.toml"
    assert Path(project.__file__).resolve().parent == project.PARENT


def test_the_brief_names_the_childs_directory() -> None:
    """The prompts name the child's files by it, not by where this repository keeps them."""
    assert project.brief()["child"] == "harness/"


def test_without_a_child_in_the_working_directory_the_scripts_stop_and_say_where_they_looked(
    tmp_path: Path,
) -> None:
    done = subprocess.run(  # noqa: S603 - the repository's own script, no input
        [sys.executable, str(HARNESS / "project.py"), "brief"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert str(tmp_path / "harness" / "project.toml") in done.stderr


def _parent(tmp_path: Path) -> Path:
    """The scripts and the engine's definitions, copied to a directory outside the repository,
    as the skill will hold them."""
    parent = tmp_path / "parent"
    parent.mkdir()
    for script in SCRIPTS:
        shutil.copy(script, parent)
    shutil.copytree(HARNESS / "lenses", parent / "lenses")
    return parent


def _outcome(
    scripts: Path, command: tuple[str, ...], run: str | None, work: Path
) -> tuple[int, str, dict[str, str]]:
    """What a script prints and writes, run from the repository's root on a fresh copy of a
    committed run (or an empty run directory), the copy at the same path each time and with
    the run's name, which tells triage the lens."""
    target = work / "runs" / (run or "new")
    shutil.rmtree(target, ignore_errors=True)
    if run:
        shutil.copytree(RUNS / run, target)
    else:
        target.mkdir(parents=True)
    name, *rest = command
    done = subprocess.run(  # noqa: S603 - the pipeline's scripts on committed runs
        [sys.executable, str(scripts / name), *(str(target) if a == "<run>" else a for a in rest)],
        cwd=project.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    written = {
        path.relative_to(target).as_posix(): _steady(path)
        for path in sorted(target.rglob("*"))
        if path.is_file()
    }
    return done.returncode, done.stdout + done.stderr, written


def _steady(path: Path) -> str:
    """A file as written, but for the code lens's untested lines: they come from a coverage
    run of the tests, which in a full run of the suite has differed between two runs a minute
    apart. That they are read at all is held."""
    text = path.read_text(encoding="utf-8")
    if path.name != "modules.jsonl":
        return text
    records = [json.loads(line) for line in text.splitlines()]
    for record in records:
        hints = record.get("hints", {})
        if "untested" in hints:
            assert isinstance(hints["untested"], dict | list)
            hints["untested"] = "read"
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records)


# Each script that runs without git branches, docker or mutmut, on a run of each lens it
# reads; the gate, the cleanup and mutation take the repository from the same place
CASES = [
    (("project.py", "brief"), None),
    (("engine.py", "--check"), None),
    (("inventory.py", "<run>"), None),
    (("surface.py", "<run>"), None),
    (("documents.py", "<run>"), None),
    (("modules.py", "<run>"), None),
    (("triage.py", "<run>"), "2026-11-12-tests-2"),
    (("triage.py", "<run>"), "2026-11-16-security"),
    (("triage.py", "<run>"), "2026-11-17-docs"),
    (("triage.py", "<run>"), "2026-11-20-code-4"),
    (("sweep.py", "<run>"), "2026-11-14-tests-2"),
    (("plan.py", "<run>"), "2026-11-20-code"),
    (("outcomes.py", "<run>"), "2026-11-20-code"),
]


@pytest.mark.parametrize(("command", "run"), CASES, ids=[f"{c[0]}-{r or 'new'}" for c, r in CASES])
def test_a_script_copied_outside_the_repository_does_what_it_does_here(
    command: tuple[str, ...], run: str | None, tmp_path: Path
) -> None:
    here = _outcome(HARNESS, command, run, tmp_path)
    assert here[0] == 0, here[1]
    assert _outcome(_parent(tmp_path), command, run, tmp_path) == here


def _strings(source: str) -> list[tuple[int, str]]:
    """A script's string literals, its docstrings left out."""
    tree = ast.parse(source)
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


@pytest.mark.parametrize(
    "script", [s for s in SCRIPTS if s.name != "project.py"], ids=lambda p: p.name
)
def test_only_the_project_file_says_where_the_repository_and_its_child_are(
    script: Path,
) -> None:
    source = script.read_text(encoding="utf-8")
    names = {node.id for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Name)}
    assert "__file__" not in names
    named = [f"{line}: {text!r}" for line, text in _strings(source) if "harness" in text]
    assert named == []


def _prompts(script: Path) -> str:
    """A workflow without its meta block and its comment lines: what its agents are told."""
    text = script.read_text(encoding="utf-8")
    body = text.split("\n}\n", 1)[1] if text.startswith("export const meta") else text
    return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("//"))


@pytest.mark.parametrize("script", WORKFLOWS, ids=lambda p: p.name)
def test_no_prompt_names_where_this_repository_keeps_the_pipeline(script: Path) -> None:
    found = [line.strip() for line in _prompts(script).splitlines() if "harness/" in line]
    assert found == []


def test_the_prompts_are_read_without_their_meta_block() -> None:
    script = WORKFLOWS[0]
    assert "whenToUse" not in _prompts(script)
    assert re.search(r"\bconst B = args\.brief\b", _prompts(script))
