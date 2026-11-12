"""The tests lens's triage (ADR-008): checks every record of a run's `findings.jsonl`, gives
each its key, sets aside what `harness/suppressions.jsonl` lists (as tracked while the
backlog item it names is open, else as suppressed), and writes `report.md` with the
confirmed findings sorted into fix and proposal, and `fixes.jsonl` for the fix stage.
Deterministic; the agents' records are data here, never instructions.

    uv run python harness/triage.py harness/runs/<date>-tests
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS = ROOT / "harness" / "suppressions.jsonl"
BACKLOG = ROOT / "docs" / "backlog"
KINDS = {"dod-gap", "mutant-gap", "weak-test"}
CLASSES = {"fix", "proposal", "drop"}
TEXT_FIELDS = ("kind", "location", "claim", "evidence", "proposal")
MUTANT = re.compile(r"^enterich\.[\w.ǁ]+__mutmut_\d+$")


def _records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [cast("dict[str, Any]", json.loads(line)) for line in lines if line.strip()]


def _number(mutant: str) -> int:
    tail = mutant.rpartition("__mutmut_")[2]
    return int(tail) if tail.isdigit() else 0


def key(record: dict[str, Any]) -> str:
    """What a suppression names: a mutant gap's lowest mutant, since one function can have
    several gaps; else the kind and location (a Definition of Done item, or a test)."""
    if record.get("kind") == "mutant-gap" and record.get("mutants"):
        mutants = cast("list[str]", record["mutants"])
        lowest = min(mutants, key=lambda m: (m.rpartition("__mutmut_")[0], _number(m)))
        return f"mutant-gap:{lowest}"
    return f"{record.get('kind')}:{record.get('location')}"


def slug(record: dict[str, Any]) -> str:
    """The fix branch's name after `auto/tests-`, from the key: `shapes-page-9`,
    `req-001-prs-f014-item-3`, `test-shapes-test-a-page-is-cut`."""
    kind, _, rest = key(record).partition(":")
    if kind == "mutant-gap":
        name, _, number = rest.removeprefix("enterich.").rpartition("__mutmut_")
        words = [w.removeprefix("x_").replace("ǁ", " ") for w in name.split(".")]
        text = f"{' '.join(words)} {number}"
    elif kind == "dod-gap":
        text = rest.partition("#")[2]
    else:
        path, _, test = rest.partition("::")
        text = f"{Path(path).stem} {test}"
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].rstrip("-")


def check(record: dict[str, Any]) -> list[str]:
    """What is wrong with a record; empty when it can be triaged."""
    problems = [f"{f} missing" for f in TEXT_FIELDS if not isinstance(record.get(f), str)]
    if record.get("kind") not in KINDS:
        problems.append(f"kind {record.get('kind')!r}")
    requirement = record.get("requirement")
    if requirement is not None and not isinstance(requirement, str):
        problems.append("requirement not a string")
    mutants = record.get("mutants")
    if record.get("kind") == "mutant-gap" and not (
        isinstance(mutants, list)
        and mutants
        and all(isinstance(m, str) and MUTANT.match(m) for m in cast("list[Any]", mutants))
    ):
        problems.append("mutants missing: the survivors' ids in full")
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


def _row(record: dict[str, Any]) -> str:
    def cell(text: str) -> str:
        # An escaped [ keeps a quoted list such as [["company", "=", …]] from reading as
        # a wiki link to the link check
        return text.replace("|", "\\|").replace("\n", " ").replace("[", "\\[")

    requirement = record.get("requirement") or ""
    return (
        f"| `{cell(record['location'])}` | {cell(requirement)} | {cell(record['claim'])} "
        f"| {cell(record['proposal'])} |"
    )


def main(run: Path, suppressions: Path = SUPPRESSIONS, backlog: Path = BACKLOG) -> int:
    records = _records(run / "findings.jsonl")
    bad = [(key(r), p) for r in records if (p := check(r))]
    bad += [
        (k, ["two records with this key"]) for k, n in Counter(map(key, records)).items() if n > 1
    ]
    if bad:
        for k, problems in bad:
            print(f"{k}: {', '.join(problems)}", file=sys.stderr)
        return 1
    # An item counts as open while its file is in the backlog, not in its archive
    # so a finding tracked there comes back once the item is done; one without an item stays
    listed = _records(suppressions)
    dropped = {s["key"] for s in listed if not s.get("backlog")}
    open_items = {
        s["key"] for s in listed if s.get("backlog") and (backlog / s["backlog"]).is_file()
    }
    confirmed = [r for r in records if r["verdict"]["confirmed"]]
    suppressed = [r for r in confirmed if key(r) in dropped]
    tracked = [r for r in confirmed if key(r) in open_items and key(r) not in dropped]
    acted_on = [r for r in confirmed if r not in suppressed and r not in tracked]
    by_class = {c: [r for r in acted_on if r["verdict"]["class"] == c] for c in CLASSES}
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
        f"Suppressed: {len(suppressed)}. Tracked in the backlog: {len(tracked)}.",
    ]
    for title, cls in (("Fix", "fix"), ("Proposal", "proposal")):
        lines += ["", f"## {title} ({len(by_class[cls])})", ""]
        if by_class[cls]:
            lines += ["| Location | Requirement | Claim | Proposal |", "| :- | :- | :- | :- |"]
            lines += [_row(r) for r in sorted(by_class[cls], key=key)]
    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # The fix stage's input: each fix with its branch's slug and its mutants' diffs
    diffs = {s["id"]: s["diff"] for s in _records(run / "survivors.jsonl")}
    with (run / "fixes.jsonl").open("w", encoding="utf-8") as out:
        for r in sorted(by_class["fix"], key=key):
            mutants = cast("list[str]", r.get("mutants") or [])
            handover = {
                "key": key(r),
                "slug": slug(r),
                **r,
                "diffs": {m: diffs[m] for m in mutants if m in diffs},
            }
            out.write(json.dumps(handover, ensure_ascii=False) + "\n")
    print(
        f"{len(records)} findings, {len(confirmed)} confirmed, {len(by_class['fix'])} to fix: "
        "report.md and fixes.jsonl written"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
