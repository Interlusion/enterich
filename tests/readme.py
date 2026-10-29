"""The README's tool list, generated from the tool-list snapshot, each area under its
name and scope from the specs index. A test checks that the README holds it;
`uv run python -m tests.readme` writes it."""

import json
import re
from pathlib import Path
from typing import Any

from erpel.tools import (
    bank_and_cash,
    master_data,
    order_to_cash,
    procure_to_pay,
    record_to_report,
)

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"
SNAPSHOT = ROOT / "tests" / "snapshots" / "tools.json"
SPECS = ROOT / "docs" / "specs" / "README.md"
START, END = "<!-- tools:start -->", "<!-- tools:end -->"
# Each area's operations and its spec file, in the specs index's order
AREAS = (
    (master_data, "req-003-master-data.md"),
    (order_to_cash, "req-004-order-to-cash.md"),
    (procure_to_pay, "req-005-procure-to-pay.md"),
    (record_to_report, "req-006-record-to-report.md"),
    (bank_and_cash, "req-007-bank-and-cash.md"),
)
# A specs index row: | [REQ-004](req-004-….md) | Order to cash: customers, … | Status |
INDEX_ROW = re.compile(r"^\| \[(REQ-\d{3})\]\(([^)]+)\) \| ([^:|]+): ([^|]+?) \|", re.MULTILINE)
# An operation's kind, as the README names it and as its annotations say it (REQ-001-PRS-NF002)
KINDS = {
    "read": ("read", True, False),
    "create": ("create draft", False, False),
    "update": ("update draft", False, True),
}


def _tools() -> dict[str, dict[str, Any]]:
    """The snapshot's tools by name; they must be the areas' operations."""
    tools = {t["name"]: t for t in json.loads(SNAPSHOT.read_text())}
    named = {op.name for module, _ in AREAS for op in module.OPERATIONS}
    if named != tools.keys():
        raise ValueError(
            "The areas' operations and tests/snapshots/tools.json differ in "
            f"{', '.join(sorted(named ^ tools.keys()))}; update the snapshot first "
            "(`uv run pytest --snapshot-update`)."
        )
    return tools


def _specs() -> dict[str, tuple[str, str, str]]:
    """Per spec file in the specs index: its ID, its area's name and what the area covers."""
    rows = INDEX_ROW.findall(SPECS.read_text())
    specs = {path: (spec, area, covers) for spec, path, area, covers in rows}
    missing = [path for _, path in AREAS if path not in specs]
    if missing:
        raise ValueError(f"docs/specs/README.md has no area row for {', '.join(missing)}.")
    return specs


def render() -> str:
    """The block between the markers: per area, its operations in their order, with the
    snapshot's title and the kind its annotations give."""
    tools, specs = _tools(), _specs()
    lines = [
        START,
        "",
        f"Erpel offers {len(tools)} tools. A deployment may offer fewer "
        "([`ERPEL_TOOLS`](docs/guides/configuration.md)); every tool works on one company, "
        "within the rights ERPNext gives the agent user.",
    ]
    for module, path in AREAS:
        spec, area, covers = specs[path]
        lines += ["", f"### {area} ([{spec}](docs/specs/{path}))", ""]
        lines += [f"{covers[0].upper()}{covers[1:]}.", ""]
        lines += ["| Tool | Title | Kind |", "| :- | :- | :- |"]
        for op in module.OPERATIONS:
            tool = tools[op.name]
            kind, read_only, destructive = KINDS[op.kind]
            hints = tool["annotations"]
            # Only a write says whether it is destructive.
            if hints["readOnlyHint"] != read_only or (
                not read_only and hints.get("destructiveHint") != destructive
            ):
                raise ValueError(f"{op.name}: its annotations don't say {op.kind}")
            lines.append(f"| `{op.name}` | {tool['title']} | {kind} |")
    return "\n".join([*lines, "", END])


def _bounds(text: str) -> tuple[int, int]:
    """Where the block starts and ends: one start marker, then one end marker."""
    if text.count(START) != 1 or text.count(END) != 1 or text.index(START) > text.index(END):
        raise ValueError(f"README.md needs one {START} followed by one {END}.")
    return text.index(START), text.index(END) + len(END)


def current() -> str:
    text = README.read_text()
    start, end = _bounds(text)
    return text[start:end]


def write() -> None:
    text = README.read_text()
    start, end = _bounds(text)
    README.write_text(text[:start] + render() + text[end:])


if __name__ == "__main__":
    write()
