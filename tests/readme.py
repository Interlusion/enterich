"""The README's tool list, generated from the tool-list snapshot. A test checks that the
README holds it; `uv run python -m tests.readme` writes it."""

import json
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
START, END = "<!-- tools:start -->", "<!-- tools:end -->"
# Each area's operations and its spec, in the specs index's order
AREAS = (
    (master_data, "Master data", "REQ-003", "req-003-master-data.md"),
    (order_to_cash, "Order to cash", "REQ-004", "req-004-order-to-cash.md"),
    (procure_to_pay, "Procure to pay", "REQ-005", "req-005-procure-to-pay.md"),
    (record_to_report, "Record to report", "REQ-006", "req-006-record-to-report.md"),
    (bank_and_cash, "Bank and cash", "REQ-007", "req-007-bank-and-cash.md"),
)
# An operation's kind, as the README names it and as its annotations say it (REQ-001-PRS-NF002)
KINDS = {
    "read": ("read", True, False),
    "create": ("create draft", False, False),
    "update": ("update draft", False, True),
}


def _tools() -> dict[str, dict[str, Any]]:
    """The snapshot's tools by name; they must be the areas' operations."""
    tools = {t["name"]: t for t in json.loads(SNAPSHOT.read_text())}
    named = {op.name for module, *_ in AREAS for op in module.OPERATIONS}
    if named != tools.keys():
        raise ValueError(
            "The areas' operations and tests/snapshots/tools.json differ in "
            f"{', '.join(sorted(named ^ tools.keys()))}; update the snapshot first "
            "(`uv run pytest --snapshot-update`)."
        )
    return tools


def render() -> str:
    """The block between the markers: per area, its operations in their order, with the
    snapshot's title and the kind its annotations give."""
    tools = _tools()
    lines = [
        START,
        "",
        f"Erpel offers {len(tools)} tools. A deployment may offer fewer "
        "([`ERPEL_TOOLS`](docs/guides/configuration.md)); every tool works on one company, "
        "within the rights ERPNext gives the agent user.",
    ]
    for module, area, spec, path in AREAS:
        lines += ["", f"### {area} ([{spec}](docs/specs/{path}))", ""]
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
