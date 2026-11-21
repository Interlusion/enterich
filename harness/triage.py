"""Triage (ADR-008), for the tests, security, docs and code lenses: checks every record of a
run's `findings.jsonl`, gives each its key, sets aside what `harness/suppressions.jsonl`
lists (as tracked while the backlog item it names is open, else as suppressed), and writes
`report.md` with the
confirmed findings sorted into fix and proposal, and `fixes.jsonl` for the fix stage.
A pattern of `harness/patterns.jsonl` that the verdicts name in three or more findings
across at least two files becomes a ratchet in `ratchets.jsonl`: one generic test for the
class, before its findings.
A run's lens is in its directory's name (`<date>-security`), and its findings are of that
lens's kinds. A security finding names its promise (`harness/promises.jsonl`), a drift its
document's record (`harness/documents.jsonl`), a code finding its survey's
(`harness/modules.jsonl`); a breach is confirmed only with how it was reproduced, a drift
and a code finding only with both sides shown, and a code finding is a fix only with the
test that shows it wrong: a restructure without one is a proposal.
Deterministic; the agents' records are data here, never instructions.

    uv run python harness/triage.py harness/runs/<date>-<lens>
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Collection
from pathlib import Path
from typing import Any, cast

try:
    from harness import engine, project
    from harness.jsonl import read as _records
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import engine  # type: ignore[import-not-found, no-redef]
    import project  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]

ROOT = Path(__file__).resolve().parent.parent
SUPPRESSIONS = ROOT / "harness" / "suppressions.jsonl"
BACKLOG = ROOT / project.SOURCES["backlog"]
PATTERNS = ROOT / "harness" / "patterns.jsonl"
PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TEST_FILE = re.compile(rf"^{re.escape(project.SOURCES['tests'])}/[\w/]+\.py$")
# A pattern confirmed in this many findings across this many files is a class: it gets a
# ratchet. Two neighbouring findings are closed by two tests
RATCHET_FROM = 3
RATCHET_FILES = 2
PROMISES = ROOT / "harness" / "promises.jsonl"
DOCUMENTS = ROOT / "harness" / "documents.jsonl"
MODULES = ROOT / "harness" / "modules.jsonl"
# Each lens's kinds of finding: the tests lens's here, the others' in their definitions
# (harness/lenses/<lens>.toml), which their workflows are written from
LENSES = {
    "tests": {"dod-gap", "mutant-gap", "weak-test"},
    **{name: set(engine.kinds(name)) for name in engine.names()},
}
# The lenses whose findings each name one record of the lens's vocabulary
VOCABULARIES = {"security": PROMISES, "docs": DOCUMENTS, "code": MODULES}
NAMED = LENSES["security"] | LENSES["docs"] | LENSES["code"]
# A finding confirmed only with what shows it, such as a breach reproduced or a drift's two
# sides: the kinds whose definition says "shown"
SHOWN = {k for name in engine.names() for k, kind in engine.kinds(name).items() if kind["shown"]}
KINDS = {kind for kinds in LENSES.values() for kind in kinds}
CLASSES = {"fix", "proposal", "drop"}
TEXT_FIELDS = ("kind", "location", "claim", "evidence", "proposal")
PACKAGE = project.SOURCES["package"]
MUTANT = re.compile(rf"^{re.escape(PACKAGE)}\.[\w.ǁ]+__mutmut_\d+$")


def vocabulary(path: Path = PATTERNS) -> dict[str, str]:
    """The operator's classes of finding: each pattern's slug with what it means."""
    known: dict[str, str] = {}
    for record in _records(path):
        name, means = record.get("pattern"), record.get("means")
        if not (isinstance(name, str) and PATTERN.match(name)):
            raise ValueError(f"{path.name}: {name!r} is not a pattern's slug")
        if not (isinstance(means, str) and means.strip()):
            raise ValueError(f"{path.name}: {name} doesn't say what it means")
        if name in known:
            raise ValueError(f"{path.name}: {name} twice")
        known[name] = means
    return known


def lens(run: Path) -> str:
    """A run's lens, from its directory's name: `<date>-<lens>` or `<date>-<lens>-<n>`; the
    tests lens, the first, if it names none."""
    return next((part for part in run.name.split("-") if part in LENSES), "tests")


def _number(mutant: str) -> int:
    tail = mutant.rpartition("__mutmut_")[2]
    return int(tail) if tail.isdigit() else 0


def key(record: dict[str, Any]) -> str:
    """What a suppression names: a mutant gap's lowest mutant, since one function can have
    several gaps; a security finding's or a drift's kind, promise and location, since one
    function can break several promises; else the kind and location (a Definition of Done item, or a
    test)."""
    if record.get("kind") in NAMED:
        return f"{record.get('kind')}:{record.get('promise')}:{record.get('location')}"
    if record.get("kind") == "mutant-gap" and record.get("mutants"):
        mutants = cast("list[str]", record["mutants"])
        lowest = min(mutants, key=lambda m: (m.rpartition("__mutmut_")[0], _number(m)))
        return f"mutant-gap:{lowest}"
    return f"{record.get('kind')}:{record.get('location')}"


def slug(record: dict[str, Any]) -> str:
    """The fix branch's name after `auto/tests-`, from the key: `shapes-page-9`,
    `req-001-prs-f014-item-3`, `test-shapes-test-a-page-is-cut`; a security finding's or a
    drift's from its promise and place: `one-company-drafts-editable`."""
    kind, _, rest = key(record).partition(":")
    if kind in NAMED:
        path, _, name = str(record.get("location")).partition(":")
        text = f"{record.get('promise')} {Path(path).stem} {name}"
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].rstrip("-")
    if kind == "mutant-gap":
        name, _, number = rest.removeprefix(f"{PACKAGE}.").rpartition("__mutmut_")
        words = [w.removeprefix("x_").replace("ǁ", " ") for w in name.split(".")]
        text = f"{' '.join(words)} {number}"
    elif kind == "dod-gap":
        text = rest.partition("#")[2]
    else:
        path, _, test = rest.partition("::")
        text = f"{Path(path).stem} {test}"
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60].rstrip("-")


def check(
    record: dict[str, Any],
    known: Collection[str] = (),
    promises: Collection[str] = (),
    kinds: Collection[str] = KINDS,
) -> list[str]:
    """What is wrong with a record; empty when it can be triaged. A verdict's pattern is
    one of the vocabulary's (`known`), or none; a security finding's or a drift's promise
    is one of its lens's (`promises`), and no other finding names one."""
    problems = [f"{f} missing" for f in TEXT_FIELDS if not isinstance(record.get(f), str)]
    if record.get("kind") not in kinds:
        problems.append(f"kind {record.get('kind')!r}")
    named = record.get("kind") in NAMED
    promise = record.get("promise")
    if (promise not in promises) if named else (promise is not None):
        problems.append(f"promise {promise!r}")
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
    shown = verdict.get("reproduction")
    if (
        record.get("kind") in SHOWN
        and verdict.get("confirmed") is True
        and not (isinstance(shown, str) and shown.strip())
    ):
        problems.append(
            "verdict.reproduction missing: a breach is confirmed as reproduced, a drift with "
            "both sides shown"
        )
    pattern = verdict.get("pattern")
    if pattern is not None and not (isinstance(pattern, str) and pattern in known):
        problems.append(f"verdict.pattern {pattern!r}")
    # Where the closing test belongs: harness/plan.py gives a test file to one branch
    files = verdict.get("test_files")
    if files is not None and not (
        isinstance(files, list)
        and all(isinstance(f, str) and TEST_FILE.match(f) for f in cast("list[Any]", files))
    ):
        problems.append(f"verdict.test_files: test modules under {project.SOURCES['tests']}/")
    elif (
        record.get("kind") in LENSES["code"]
        and verdict.get("confirmed") is True
        and verdict.get("class") == "fix"
        and not files
    ):
        problems.append(
            "verdict.test_files missing: a code finding is a fix only with the test that shows "
            "it wrong; a restructure without one is a proposal"
        )
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


def main(
    run: Path,
    suppressions: Path = SUPPRESSIONS,
    backlog: Path = BACKLOG,
    patterns: Path = PATTERNS,
    promises: Path | None = None,
) -> int:
    known = vocabulary(patterns)
    of_lens = LENSES[lens(run)]
    promises = promises or VOCABULARIES.get(lens(run), PROMISES)
    promised = {str(p.get("promise")) for p in _records(promises) if "out" not in p}
    records = _records(run / "findings.jsonl")
    bad = [(key(r), p) for r in records if (p := check(r, known, promised, of_lens))]
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
    # A class is closed once: a pattern the fixes share across files gets a ratchet
    by_pattern: dict[str, list[dict[str, Any]]] = {}
    for r in by_class["fix"]:
        if (pattern := cast("str | None", r["verdict"].get("pattern"))) is not None:
            by_pattern.setdefault(pattern, []).append(r)
    ratchets = {
        p: rs
        for p, rs in sorted(by_pattern.items())
        if len(rs) >= RATCHET_FROM
        and len({re.split("[:#]", r["location"])[0] for r in rs}) >= RATCHET_FILES
    }
    kinds = Counter(r["kind"] for r in records)
    confirmed_kinds = Counter(r["kind"] for r in confirmed)
    lines = [
        f"# {lens(run).capitalize()} lens: {run.name}",
        "",
        "| Kind | Found | Confirmed |",
        "| :- | -: | -: |",
        *(f"| {k} | {kinds[k]} | {confirmed_kinds[k]} |" for k in sorted(of_lens)),
        f"| all | {len(records)} | {len(confirmed)} |",
        "",
        f"Suppressed: {len(suppressed)}. Tracked in the backlog: {len(tracked)}.",
    ]
    lines += ["", f"## Ratchet ({len(ratchets)})", ""]
    if ratchets:
        lines += ["| Pattern | Findings | Means |", "| :- | -: | :- |"]
        lines += [f"| `{p}` | {len(rs)} | {known[p]} |" for p, rs in ratchets.items()]
    for title, cls in (("Fix", "fix"), ("Proposal", "proposal")):
        lines += ["", f"## {title} ({len(by_class[cls])})", ""]
        if by_class[cls]:
            lines += ["| Location | Requirement | Claim | Proposal |", "| :- | :- | :- | :- |"]
            lines += [_row(r) for r in sorted(by_class[cls], key=key)]
    (run / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # The fix stage's input: each ratchet with its findings' keys, then each fix with its
    # branch's slug, its ratchet if it has one, and its mutants' diffs
    with (run / "ratchets.jsonl").open("w", encoding="utf-8") as out:
        for p, rs in ratchets.items():
            ratchet = {
                "key": f"ratchet:{p}",
                "slug": f"ratchet-{p}",
                "pattern": p,
                "means": known[p],
                "findings": sorted(key(r) for r in rs),
            }
            out.write(json.dumps(ratchet, ensure_ascii=False) + "\n")
    diffs = {s["id"]: s["diff"] for s in _records(run / "survivors.jsonl")}
    with (run / "fixes.jsonl").open("w", encoding="utf-8") as out:
        for r in sorted(by_class["fix"], key=key):
            mutants = cast("list[str]", r.get("mutants") or [])
            # After the record's own fields: a record can't name its key or its branch
            handover = {
                **r,
                "key": key(r),
                "slug": slug(r),
                "ratchet": p if (p := r["verdict"].get("pattern")) in ratchets else None,
                "diffs": {m: diffs[m] for m in mutants if m in diffs},
            }
            out.write(json.dumps(handover, ensure_ascii=False) + "\n")
    print(
        f"{len(records)} findings, {len(confirmed)} confirmed, {len(by_class['fix'])} to fix, "
        f"{len(ratchets)} ratchets: report.md, fixes.jsonl and ratchets.jsonl written"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
