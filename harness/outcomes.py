"""The fix stage's outcomes (ADR-008): checks every record of a run's `outcomes.jsonl`, the
fix workflow's result for each fix and ratchet as `harness/record.py` wrote it, against the run's
`fixes.jsonl` and `ratchets.jsonl`, gives each its state, and writes `outcomes.json`: the
counts, those without an outcome, per branch the commits of those no review accepted, which
are dropped by hand, and per branch the commits of those a review accepted, the only ones
the gate lets through. Deterministic; the agents' records are data here, never instructions.

    uv run python harness/outcomes.py harness/runs/<date>-tests
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, cast

try:
    from harness.jsonl import read as _records
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]

STATUSES = {"committed", "proposal", "refuted", "elsewhere"}
# In the order of a fix's way: what the review said, what the fix agent said, no answer
STATES = ("accepted", "rejected", "unreviewed", "refuted", "proposal", "elsewhere", "failed")
NOT_ACCEPTED = {"rejected", "unreviewed"}
COMMIT = re.compile(r"^[0-9a-f]{7,40} \S")


def _strings(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in cast("list[Any]", value))


def state(record: dict[str, Any]) -> str:
    """Where a fix ended: by its review if it committed, else by what the fix agent said.
    No answer from the fix agent, or "committed" without a commit, is a failed fix."""
    fixed, review = record.get("fixed"), record.get("review")
    if not isinstance(fixed, dict):
        return "failed"
    fixed = cast("dict[str, Any]", fixed)
    if fixed.get("status") != "committed":
        return str(fixed.get("status"))
    if not fixed.get("commits"):
        return "failed"
    if not isinstance(review, dict):
        return "unreviewed"
    return "accepted" if cast("dict[str, Any]", review).get("accept") is True else "rejected"


def check(record: dict[str, Any]) -> list[str]:
    """What is wrong with a record; empty when it can be counted."""
    problems = [
        f"{f} missing" for f in ("key", "slug", "branch") if not isinstance(record.get(f), str)
    ]
    branch = record.get("branch")
    if isinstance(branch, str) and not branch.startswith("auto/"):
        problems.append(f"{branch} is not an auto/ branch")
    fixed, review = record.get("fixed"), record.get("review")
    if isinstance(fixed, dict):
        fixed = cast("dict[str, Any]", fixed)
        if fixed.get("status") not in STATUSES:
            problems.append(f"fixed.status {fixed.get('status')!r}")
        commits = fixed.get("commits")
        if not (_strings(commits) and all(COMMIT.match(c) for c in cast("list[str]", commits))):
            problems.append("fixed.commits: each '<hash> <subject>'")
        if not _strings(fixed.get("tests")):
            problems.append("fixed.tests not a list of strings")
        problems += [
            f"fixed.{f} missing" for f in ("red", "notes") if not isinstance(fixed.get(f), str)
        ]
    elif fixed is not None:
        problems.append("fixed not an object")
    if isinstance(review, dict):
        review = cast("dict[str, Any]", review)
        if not isinstance(review.get("accept"), bool):
            problems.append("review.accept not a boolean")
        if not _strings(review.get("problems")):
            problems.append("review.problems not a list of strings")
        if not isinstance(review.get("reason"), str):
            problems.append("review.reason missing")
        if not problems and state({**record, "review": None}) != "unreviewed":
            problems.append("a review of a fix that committed nothing")
    elif review is not None:
        problems.append("review not an object")
    return problems


def main(run: Path) -> int:
    records = _records(run / "outcomes.jsonl")
    handover = [*_records(run / "fixes.jsonl"), *_records(run / "ratchets.jsonl")]
    handed = {str(f.get("key")) for f in handover}
    keys = [str(r.get("key")) for r in records]
    bad = [(k, p) for k, r in zip(keys, records, strict=True) if (p := check(r))]
    bad += [(k, ["two records with this key"]) for k, n in Counter(keys).items() if n > 1]
    bad += [(k, ["not among the run's fixes and ratchets"]) for k in sorted(set(keys) - handed)]
    if bad:
        for k, problems in bad:
            print(f"{k}: {', '.join(problems)}", file=sys.stderr)
        return 1
    states = Counter(state(r) for r in records)
    # A fix no review accepted is dropped from its branch; the gate refuses one left there
    unaccepted: dict[str, list[str]] = {}
    accepted: dict[str, list[str]] = {}
    for r in records:
        fixed = cast("dict[str, Any]", r.get("fixed") or {})
        hashes = [c.split(" ", 1)[0] for c in cast("list[str]", fixed.get("commits") or [])]
        if state(r) in NOT_ACCEPTED:
            unaccepted.setdefault(cast("str", r["branch"]), []).extend(hashes)
        elif state(r) == "accepted":
            accepted.setdefault(cast("str", r["branch"]), []).extend(hashes)
    summary = {
        "fixes": len(handed),
        "states": {s: states[s] for s in STATES if states[s]},
        "missing": sorted(handed - set(keys)),
        "unaccepted": unaccepted,
        "accepted": accepted,
    }
    (run / "outcomes.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("fixes", "states")}))
    for name in ("missing", "unaccepted"):
        if summary[name]:
            print(f"{name}: {json.dumps(summary[name])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
