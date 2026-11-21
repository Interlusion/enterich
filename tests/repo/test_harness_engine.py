"""The security, docs and code lenses share one survey and verify engine (analysis 004,
section 3.2): `harness/engine.py` writes each lens's workflow from the engine's template and
the lens's definition, so the engine is written once and a lens is what differs."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

from harness import engine, modules, triage

WORKFLOWS = engine.ROOT / ".claude" / "workflows"


def test_every_lens_with_a_survey_engine_has_a_definition() -> None:
    """The tests lens has a workflow of its own shape; every other lens is a definition."""
    assert sorted(engine.names()) == sorted(set(triage.LENSES) - {"tests"})


@pytest.mark.parametrize("name", engine.names())
def test_the_workflow_is_what_its_definition_writes(name: str) -> None:
    """An edit to a generated workflow would be lost at the next writing: edit the definition."""
    written = (WORKFLOWS / f"improve-{name}.js").read_text(encoding="utf-8")
    assert engine.render(name) == written


@pytest.mark.parametrize("name", engine.names())
def test_a_definition_fills_every_slot_of_the_template_and_no_other(name: str) -> None:
    definition = engine.definition(name)
    assert sorted(definition) == sorted((*engine.SLOTS, *engine.DATA))


def test_a_slot_left_unfilled_or_unknown_stops_the_writing() -> None:
    definition = engine.definition("security")
    with pytest.raises(engine.DefinitionError, match="units_arg"):
        engine.fill({k: v for k, v in definition.items() if k != "units_arg"})
    with pytest.raises(engine.DefinitionError, match="surplus"):
        engine.fill({**definition, "surplus": "x"})


@pytest.mark.parametrize("name", engine.names())
def test_a_prompt_names_only_what_its_workflow_has(name: str) -> None:
    """A name in a prompt's ${...} that the workflow doesn't define fails only when it runs."""
    definition = engine.definition(name)
    script = engine.render(name)
    defined = set(re.findall(r"\bconst (\w+)", script))
    # The verified finding, the survey's unit, and what JavaScript has without a definition
    known = defined | {"f", str(definition["survey_param"]), "JSON", "Object", "null"}
    texts = [str(definition[slot]) for slot in engine.PROMPTS]
    used = {
        word
        for text in texts
        for expression in re.findall(r"\$\{([^{}]*)\}", text)
        for word in re.findall(r"(?<![.\w])([A-Za-z_]\w*)", expression)
    }
    assert used - known == set()


# A lens's kinds of finding are in its definition, once: the workflow's schema and prompts,
# triage and the code lens's inventory take them from there


@pytest.mark.parametrize("name", engine.names())
def test_every_kind_says_whether_only_showing_it_confirms_it(name: str) -> None:
    kinds = engine.kinds(name)
    assert kinds
    assert all(isinstance(kind.get("shown"), bool) for kind in kinds.values())


def test_triage_takes_the_lenses_kinds_from_their_definitions() -> None:
    for name in engine.names():
        assert triage.LENSES[name] == set(engine.kinds(name))
    shown = {k for n in engine.names() for k, kind in engine.kinds(n).items() if kind["shown"]}
    assert shown == triage.SHOWN
    assert "unproven" not in triage.SHOWN


def test_the_code_lens_inventory_takes_its_concerns_from_the_definition() -> None:
    concerns = engine.kinds("code")
    local = tuple(k for k, c in concerns.items() if c["scope"] == "local")
    across = tuple(k for k, c in concerns.items() if c["scope"] == "across")
    assert (local, across) == (modules.LOCAL, modules.ACROSS)
    assert tuple(concerns) == modules.CONCERNS
    assert local
    assert across


@pytest.mark.parametrize("name", engine.names())
def test_the_workflow_offers_exactly_the_definitions_kinds(name: str) -> None:
    """The kinds the schema allows, or the one the script sets, are the definition's."""
    script = engine.render(name)
    kinds = list(engine.kinds(name))
    if "Object.keys(CONCERNS)" in script:
        offered = re.findall(r"^  '([\w-]+)': \{$", script, re.MULTILINE)
    elif "kind: {\n            enum: [" in script:
        offered = re.findall(r"'([\w-]+)'", script.split("enum: [", 1)[1].split("]", 1)[0])
    else:
        offered = re.findall(r"kind: '([\w-]+)'", script)
    assert offered == kinds


def test_a_kind_named_in_a_value_that_the_engine_does_not_derive_stops_the_writing() -> None:
    definition = engine.definition("docs")
    with pytest.raises(engine.DefinitionError, match="nonsense"):
        engine.fill({**definition, "found": "@@nonsense@@"})
    with pytest.raises(engine.DefinitionError, match="one kind"):
        engine.fill({**engine.definition("security"), "found": "kind: @@kind@@"})


def test_check_finds_a_workflow_edited_by_hand(tmp_path: Path) -> None:
    for name in engine.names():
        (tmp_path / f"improve-{name}.js").write_text(engine.render(name), encoding="utf-8")
    assert engine.stale(tmp_path) == []
    edited = tmp_path / "improve-docs.js"
    edited.write_text(edited.read_text(encoding="utf-8") + "// by hand\n", encoding="utf-8")
    assert engine.stale(tmp_path) == ["improve-docs.js"]


def test_the_check_runs_from_the_command_line() -> None:
    done = subprocess.run(
        [sys.executable, "harness/engine.py", "--check"],
        cwd=engine.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
