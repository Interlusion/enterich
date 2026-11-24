"""This repository's values for the improvement pipeline, from `harness/project.toml`: the
one place the scripts read them from (analysis 003, section 3.6). A value of the wrong form
stops every script at its import, rather than letting a check pass that reads nothing.

It is also the one place that says where things are (analysis 004, section 3.1, step 2):
the repository is the working directory the scripts run from, its child (the repository's
own files for the pipeline: this file, the vocabularies, the suppressions and the runs) is
`harness/` there, and the method's own files, such as the engine's definitions, lie beside
the scripts. No script finds the repository from where it lies, so the scripts work from the
skill's directory as they work from this repository's."""

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path.cwd().resolve()
CHILD = ROOT / "harness"
PARENT = Path(__file__).resolve().parent
FILE = CHILD / "project.toml"
# Directories, written without a trailing slash
PATHS = ("specs", "tests", "code", "backlog")
LISTS = {
    "sources": ("dod_closing", "tests_left_out"),
    "docs": ("scope",),
    "gate": ("commit_types", "allowed_besides", "forbidden", "forbidden_names"),
}
# The code lens's hints: whole numbers above 0
NUMBERS = {"code": ("complexity", "literal_length", "number_size")}
# The gate's order rule reads these types: a fix, feature or refactor right after its test
ORDERED = {"test", "fix", "feat", "refactor"}


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(
        isinstance(v, str) and v for v in cast("list[object]", value)
    )


def problems(values: dict[str, Any]) -> list[str]:
    """What is wrong with the file's values; empty when the scripts can read them."""
    found: list[str] = []
    for section, keys in LISTS.items():
        found += [
            f"{section}.{key}: a list of strings"
            for key in keys
            if not _strings(values.get(section, {}).get(key))
        ]
    for section, keys in NUMBERS.items():
        found += [
            f"{section}.{key}: a whole number above 0"
            for key in keys
            if not (
                isinstance(n := values.get(section, {}).get(key), int)
                and not isinstance(n, bool)
                and n > 0
            )
        ]
    sources = cast("dict[str, Any]", values.get("sources", {}))
    found += [
        f"sources.{key}: a directory without a trailing slash"
        for key in PATHS
        if not (isinstance(sources.get(key), str) and sources[key] and sources[key][-1] != "/")
    ]
    try:
        if re.compile(str(sources.get("requirement_id"))).groups:
            found.append("sources.requirement_id: no capturing group, use (?:…)")
    except re.error:
        found.append("sources.requirement_id: not a regular expression")
    gate = cast("dict[str, Any]", values.get("gate", {}))
    checks = cast("dict[str, Any]", gate.get("checks") or {})
    if "tests" not in checks:
        found.append("gate.checks: no tests, the check whose results the gate compares with main's")
    found += [f"gate.checks.{n}: a list of strings" for n, c in checks.items() if not _strings(c)]
    brief = cast("dict[str, Any]", values.get("brief", {}))
    found += [f"brief.{k}: a phrase" for k, v in brief.items() if not (isinstance(v, str) and v)]
    missing = ORDERED - set(cast("list[str]", gate.get("commit_types") or []))
    if missing:
        found.append(f"gate.commit_types: without {', '.join(sorted(missing))}")
    return found


if not FILE.is_file():
    sys.exit(f"{FILE} is missing: run the pipeline's scripts from the repository's root")
_values = cast("dict[str, dict[str, Any]]", tomllib.loads(FILE.read_text(encoding="utf-8")))
if _wrong := problems(_values):
    raise ValueError(f"{FILE.name}: {'; '.join(_wrong)}")
SOURCES = _values["sources"]
SECURITY = _values["security"]
DOCS = _values["docs"]
CODE = _values["code"]
GATE = _values["gate"]
BRIEF = _values["brief"]


def strings(section: dict[str, Any], key: str) -> tuple[str, ...]:
    """A list of the file, which problems() checked, as a tuple."""
    return tuple(cast("list[str]", section[key]))


def allowed() -> tuple[str, ...]:
    """What a fix branch may change: the tests, the code, and what the gate allows besides."""
    besides = strings(GATE, "allowed_besides")
    return (f"{SOURCES['tests']}/", f"{SOURCES['code']}/", *besides)


def brief() -> dict[str, str]:
    """What the workflows' prompts say about this repository: the file's [brief], with the
    paths and lists the scripts read too, so the prompts and the gate name the same ones."""
    *first, last = allowed()
    return {
        **cast("dict[str, str]", BRIEF),
        "code": f"{SOURCES['code']}/",
        "tests": f"{SOURCES['tests']}/",
        "specs": f"{SOURCES['specs']}/",
        "policy": SECURITY["policy"],
        "may_change": f"{', '.join(first)} and {last}",
        "child": f"{CHILD.relative_to(ROOT).as_posix()}/",
    }


if __name__ == "__main__":
    import json

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["brief"], help="print the brief the workflows take")
    parser.parse_args()
    print(json.dumps(brief(), ensure_ascii=False))
