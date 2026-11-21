"""The survey and verify engine of the security, docs and code lenses (analysis 004, section
3.2): writes each lens's workflow, `.claude/workflows/improve-<lens>.js`, from the engine's
template and the lens's definition in `lenses/`, beside the scripts. A Workflow script reads
no file, so the engine is assembled here, before a run, not by the script; what differs per
run or per repository stays in the script's `${...}` and comes with its arguments, as the
brief does.

A definition fills every slot of the template, `@@name@@`, and no other. Its values are put
in as written, but for three forms: a slot inside a quoted string of the template gets its
quotes escaped, a block (a lens's own constants) is followed by a blank line where it has
any, and a list becomes the quoted names of a schema's `required`.

A definition's `[kinds]` are the lens's kinds of finding, once: whether a kind is confirmed
only as shown (`shown`), and what the workflow says of it (`means`, `bar`), read by triage and
by the code lens's inventory (`scope`) too. A value names what the engine derives from them
as `@@kind@@` (a lens of one kind), `@@kind_names@@`, `@@kind_meanings@@` or `@@concerns@@`.

    uv run python harness/engine.py            # write the workflows
    uv run python harness/engine.py --check    # which workflows differ from what it writes
"""

import re
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

try:
    from harness import project
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import project  # type: ignore[import-not-found, no-redef]

Definition = dict[str, Any]

ROOT = project.ROOT
# The method's: the template and the definitions lie beside the scripts
LENSES = project.PARENT / "lenses"
TEMPLATE = LENSES / "engine.js.tmpl"
# The repository's: where the session's Workflow tool finds them
WORKFLOWS = ROOT / ".claude" / "workflows"
SLOT = re.compile(r"@@(\w+)@@")
# Slots inside a single-quoted string of the template
QUOTED = (
    "description",
    "when_to_use",
    "survey_detail",
    "verify_detail",
    "test_files",
    "reproduction",
)
# A lens's own constants, each followed by a blank line where the lens has any
BLOCKS = ("consts", "prompt_consts")
# The prompts' text, whose ${...} the script fills when it runs
PROMPTS = ("survey_intro", "since", "survey_body", "verify")
# What a definition holds besides its slots' values
DATA = ("kinds",)


class DefinitionError(ValueError):
    """A definition that leaves a slot of the template unfilled, or fills one it hasn't."""


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


SLOTS = tuple(dict.fromkeys(SLOT.findall(_template())))


def names() -> list[str]:
    """The lenses that have a definition."""
    return sorted(path.stem for path in LENSES.glob("*.toml"))


def definition(name: str) -> Definition:
    with (LENSES / f"{name}.toml").open("rb") as file:
        return tomllib.load(file)


def kinds(name: str) -> dict[str, dict[str, Any]]:
    """A lens's kinds of finding, in the definition's order, each with what it says of it."""
    return cast("dict[str, dict[str, Any]]", definition(name)["kinds"])


def _quoted(text: str) -> str:
    """Text for a single-quoted JavaScript string."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _derived(name: str, of: dict[str, dict[str, Any]]) -> str:
    """What the engine writes from a definition's kinds where a value names it."""
    if name == "kind":
        if len(of) != 1:
            raise DefinitionError(f"@@kind@@ is for a lens of one kind, not of {list(of)}")
        return f"'{next(iter(of))}'"
    if name == "kind_names":
        return ", ".join(f"'{k}'" for k in of)
    if name == "kind_meanings":
        return _quoted("; ".join(f"{k}: {kind['means']}" for k, kind in of.items()))
    if name == "concerns":
        return "\n".join(
            f"  '{k}': {{\n    means: '{_quoted(kind['means'])}',\n"
            f"    bar: '{_quoted(kind['bar'])}',\n  }},"
            for k, kind in of.items()
        )
    raise DefinitionError(f"@@{name}@@ is nothing the engine derives from the kinds")


def _value(slot: str, value: str | list[str], of: dict[str, dict[str, Any]]) -> str:
    if isinstance(value, list):
        return ", ".join(f"'{v}'" for v in value)
    # A multi-line string ends with the line break before its closing quotes
    text = SLOT.sub(lambda m: _derived(m.group(1), of), value.removesuffix("\n"))
    if slot in QUOTED:
        return _quoted(text)
    if slot in BLOCKS:
        return f"{text}\n\n" if text else ""
    return text


def fill(values: Definition) -> str:
    """The template with every slot filled from the definition's values."""
    missing = [s for s in (*SLOTS, *DATA) if s not in values]
    surplus = [k for k in values if k not in (*SLOTS, *DATA)]
    if missing or surplus:
        raise DefinitionError(f"unfilled: {missing}; not in the template: {surplus}")
    of = cast("dict[str, dict[str, Any]]", values["kinds"])
    return SLOT.sub(lambda m: _value(m.group(1), values[m.group(1)], of), _template())


def render(name: str) -> str:
    return fill(definition(name))


def stale(directory: Path = WORKFLOWS) -> list[str]:
    """The workflows in the directory that differ from what their definitions write."""
    differ: list[str] = []
    for name in names():
        path = directory / f"improve-{name}.js"
        if not path.exists() or path.read_text(encoding="utf-8") != render(name):
            differ.append(path.name)
    return differ


def main(argv: list[str]) -> int:
    if argv == ["--check"]:
        differ = stale()
        for name in differ:
            print(f"{name} differs from its definition: write it again with engine.py")
        return 1 if differ else 0
    if argv:
        print(__doc__, file=sys.stderr)
        return 2
    for name in names():
        (WORKFLOWS / f"improve-{name}.js").write_text(render(name), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
