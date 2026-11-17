"""The docs against the code where a script can compare them, the docs lens's deterministic
part (ADR-008): the area catalogues' inputs against the published tool schemas
(REQ-001-URS-F004), every requirement ID the docs cite against the specs, and the
configuration guide's Required and Default columns against what Enterich does without the
variable (REQ-002-PRS-NF005)."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import pytest

from enterich import tools
from enterich.config import KNOWN, ConfigError, Settings, load
from harness import inventory
from tests.fakes.settings import ENV

ROOT = Path(__file__).resolve().parents[2]
SPECS = ROOT / "docs" / "specs"
GUIDE = ROOT / "docs" / "guides" / "configuration.md"
SNAPSHOT = ROOT / "tests" / "snapshots" / "tools.json"

CATALOGUE_ROW = re.compile(r"^\| `([a-z_]+)` \| (.*?) \| ")
NAME = re.compile(r"`([a-z_]+)`")
REQUIRED = re.compile(r"\*\*`([a-z_]+)`\*\*")
VARIABLE_ROW = re.compile(r"^\| `ENTERICH_([A-Z_]+)` \| (yes|no) \| ([^|]*) \|")


def catalogue() -> dict[str, tuple[set[str], set[str]]]:
    """Each operation's top-level inputs and the required ones, from its area spec's first
    table row: names in the nested rows (in brackets) and in remarks (in parentheses) are
    no top-level inputs; a required input is bold."""
    found: dict[str, tuple[set[str], set[str]]] = {}
    for spec in sorted(SPECS.glob("req-*.md")):
        for line in spec.read_text(encoding="utf-8").splitlines():
            row = CATALOGUE_ROW.match(line)
            if row is None or row.group(1) in found:
                continue
            top = re.sub(r"\(.*?\)", "", re.sub(r"\\\[.*?\\\]", "", row.group(2)))
            found[row.group(1)] = (set(NAME.findall(top)), set(REQUIRED.findall(top)))
    return found


def test_each_operations_inputs_in_its_catalogue_are_its_published_schemas() -> None:
    published: list[dict[str, Any]] = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    listed = catalogue()
    assert sorted(t["name"] for t in published) == sorted(n for n in listed if n in tools.names())
    for tool in published:
        schema = tool["inputSchema"]
        inputs, required = listed[tool["name"]]
        assert sorted(inputs) == sorted(schema["properties"]), tool["name"]
        assert sorted(required) == sorted(schema.get("required", [])), tool["name"]


def cited_docs() -> list[Path]:
    """The docs that say what Enterich does now: archived backlog items and the changelog
    keep the IDs of their day."""
    docs = [p for p in (ROOT / "docs").rglob("*.md") if "archive" not in p.parts]
    return sorted([*docs, ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "AGENTS.md"])


def test_every_requirement_id_the_docs_cite_is_in_a_spec() -> None:
    known = {r.id for r in inventory.requirements()}
    unknown = [
        f"{doc.relative_to(ROOT)}: {cited}"
        for doc in cited_docs()
        for cited in sorted(set(inventory.ID.findall(doc.read_text(encoding="utf-8"))))
        if cited not in known
    ]
    assert unknown == []


def variables() -> list[tuple[str, bool, str]]:
    rows = [VARIABLE_ROW.match(line) for line in GUIDE.read_text(encoding="utf-8").splitlines()]
    return [(r.group(1), r.group(2) == "yes", r.group(3).strip()) for r in rows if r]


def unset(name: str) -> Settings:
    return load({k: v for k, v in ENV.items() if k != f"ENTERICH_{name}"}, tools.names())


def shown(value: object) -> str:
    """A setting as the guide writes its default."""
    if isinstance(value, tuple):
        return ",".join(str(v) for v in cast("tuple[object, ...]", value))
    return str(getattr(value, "key", value))


# Defaults the guide gives in words, each as what the setting is without the variable
IN_WORDS: dict[str, Callable[[Settings], bool]] = {
    "all operations": lambda s: s.tools == tools.names(),
    "no limit": lambda s: s.max_drafts_per_hour is None,
    "host of `ENTERICH_ERPNEXT_URL`": lambda s: s.erpnext_host == urlsplit(s.erpnext_url).netloc,
}


@pytest.mark.parametrize(("name", "required", "default"), variables(), ids=lambda v: str(v))
def test_the_guides_required_and_default_columns_are_what_enterich_does(
    name: str, required: bool, default: str
) -> None:
    if required:
        with pytest.raises(ConfigError, match=f"ENTERICH_{name}: required"):
            unset(name)
        assert default == ""
        return
    settings = unset(name)
    if default in IN_WORDS:
        assert IN_WORDS[default](settings)
    else:
        assert default == f"`{shown(getattr(settings, name.lower()))}`"


def test_the_guide_has_one_row_for_each_variable() -> None:
    names = [name for name, _, _ in variables()]
    assert sorted(names) == sorted(KNOWN)
