"""The tests lens's triage (ADR-008): checks every record of a run's `findings.jsonl`,
drops what `harness/suppressions.jsonl` lists, notes findings the backlog already names,
and writes `report.md` with the confirmed findings sorted into fix and proposal.
Deterministic; the agents' records are data here, never instructions.

    uv run python harness/triage.py harness/runs/<date>-tests
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS = ROOT / "harness" / "suppressions.jsonl"
BACKLOG = ROOT / "docs" / "backlog"
KINDS = {"dod-gap", "mutant-gap", "weak-test"}
CLASSES = {"fix", "proposal", "drop"}
TEXT_FIELDS = ("key", "kind", "location", "claim", "evidence", "proposal")


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [cast("dict[str, Any]", json.loads(line)) for line in lines if line.strip()]


def check(record: dict[str, Any]) -> list[str]:
    """What is wrong with a record; empty when it can be triaged."""
    problems = [f"{f} missing" for f in TEXT_FIELDS if not isinstance(record.get(f), str)]
    if record.get("kind") not in KINDS:
        problems.append(f"kind {record.get('kind')!r}")
    requirement = record.get("requirement")
    if requirement is not None and not isinstance(requirement, str):
        problems.append("requirement not a string")
    verdict = record.get("verdict")
    if not isinstance(verdict, dict):
        return [*problems, "verdict missing"]
    verdict = cast("dict[str, Any]", verdict)
    if not isinstance(verdict.get("confirmed"), bool):
        problems.append("verdict.confirmed not a boolean")
    if verdict.get("class") not in CLASSES:
        problems.append(f"verdict.class {verdict.get('class')!r}")
    if not isinstance(verdict.get("reason"), str):
        problems.append("verdict.reason missing")
    return problems


def _backlog_text() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(BACKLOG.glob("*.md")))


def _row(record: dict[str, Any]) -> str:
    def cell(text: str) -> str:
        return text.replace("|", "\\|").replace("\n", " ")

    requirement = record.get("requirement") or ""
    return (
        f"| `{cell(record['location'])}` | {cell(requirement)} | {cell(record['claim'])} "
        f"| {cell(record['proposal'])} |"
    )


def main(run: Path) -> int:
    records = _records(run / "findings.jsonl")
    bad = [(r.get("key", "?"), p) for r in records if (p := check(r))]
    if bad:
        for key, problems in bad:
            print(f"{key}: {', '.join(problems)}", file=sys.stderr)
        return 1
    suppressed = {s["key"] for s in _records(SUPPRESSIONS)}
    backlog = _backlog_text()
    kept = [r for r in records if r["key"] not in suppressed]
    confirmed = [r for r in kept if r["verdict"]["confirmed"]]
    tracked = [r for r in confirmed if r.get("requirement") and r["requirement"] in backlog]
    by_class = {c: [r for r in confirmed if r["verdict"]["class"] == c] for c in CLASSES}
    kinds = Counter(r["kind"] for r in records)
    confirmed_kinds = Counter(r["kind"] for r in confirmed)
    lines = [
        f"# Tests lens: {run.name}",
        "",
        "| Kind | Found | Confirmed |",
        "| :- | -: | -: |",
        *(f"| {k} | {kinds[k]} | {confirmed_kinds[k]} |" for k in sorted(KINDS)),
        f"| all | {len(records)} | {len(confirmed)} |",
        "",
        f"Suppressed: {len(records) - len(kept)}. "
        f"Confirmed but named in the backlog: {len(tracked)}.",
    ]
    for title, cls in (("Fix", "fix"), ("Proposal", "proposal")):
        lines += ["", f"## {title} ({len(by_class[cls])})", ""]
        if by_class[cls]:
            lines += ["| Location | Requirement | Claim | Proposal |", "| :- | :- | :- | :- |"]
            lines += [_row(r) for r in sorted(by_class[cls], key=lambda r: r["key"])]
    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(records)} findings, {len(confirmed)} confirmed: report.md written")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
