"""This repository's values for the improvement pipeline, from `harness/project.toml`: the
one place the scripts read them from (analysis 003, section 3.6). A value of the wrong form
stops every script at its import, rather than letting a check pass that reads nothing."""

import re
import tomllib
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "harness" / "project.toml"
# Directories, written without a trailing slash
PATHS = ("specs", "tests", "code", "backlog")
LISTS = {
    "sources": ("dod_closing", "tests_left_out"),
    "docs": ("scope",),
    "gate": ("commit_types", "allowed_besides", "forbidden", "forbidden_names"),
}
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
    missing = ORDERED - set(cast("list[str]", gate.get("commit_types") or []))
    if missing:
        found.append(f"gate.commit_types: without {', '.join(sorted(missing))}")
    return found


_values = cast("dict[str, dict[str, Any]]", tomllib.loads(FILE.read_text(encoding="utf-8")))
if _wrong := problems(_values):
    raise ValueError(f"{FILE.name}: {'; '.join(_wrong)}")
SOURCES = _values["sources"]
SECURITY = _values["security"]
DOCS = _values["docs"]
GATE = _values["gate"]


def strings(section: dict[str, Any], key: str) -> tuple[str, ...]:
    """A list of the file, which problems() checked, as a tuple."""
    return tuple(cast("list[str]", section[key]))
