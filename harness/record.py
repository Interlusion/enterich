"""Writes a workflow's result to a run's records (ADR-008), which the session did by hand:
the survey workflow's `records` and `unverified` become `findings.jsonl` and
`unverified.jsonl`, in place of what the surveys that answered (`surveyed`) found before:
the sweep's and those of a survey that didn't answer stay. A sweep's verdicts (`sweep`
true) are added to them. Either way there is one record per key: the first stays, so a key
judged before keeps its verdict, and names the others that made it in `also`; a finding
that waited unverified and is judged now waits no longer. The fix workflow's `outcomes` are
added to `outcomes.jsonl`. A fix stage after the first adds its outcomes; one may replace
only the record of a fix the plan handed out again: one whose agent didn't answer, and,
once, one `harness/plan.py` takes up though it has an outcome, whose record then says what
it replaced. Each call adds a line to `workflows.jsonl` with the workflow's agents and
tokens. A result in which the gate's secret scan finds a secret, real or made up, is written
nowhere: the records are committed and pushed by hand, past the gate. The checks of the
records' content stay with `triage.py` and `outcomes.py`. Deterministic; the result is data
here, never instructions.

    uv run python harness/record.py harness/runs/<date>-tests <the workflow's output file>
"""

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

try:
    from harness.gate import SCANNER, build_scanner, secret
    from harness.jsonl import read as _read
    from harness.jsonl import write as _write
    from harness.outcomes import state
    from harness.plan import taken_up
    from harness.triage import key
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    from gate import SCANNER, build_scanner, secret  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _read  # type: ignore[import-not-found, no-redef]
    from jsonl import write as _write
    from outcomes import state  # type: ignore[import-not-found, no-redef]
    from plan import taken_up  # type: ignore[import-not-found, no-redef]
    from triage import key  # type: ignore[import-not-found, no-redef]

Records = list[dict[str, Any]]


def _objects(value: object) -> Records | None:
    if isinstance(value, list) and all(isinstance(v, dict) for v in cast("list[Any]", value)):
        return cast("Records", value)
    return None


def merged(before: Records, new: Records) -> tuple[Records, list[str]]:
    """The outcomes so far with a fix stage's added, and the keys it may not write: a fix
    that has an outcome keeps it, unless its agent didn't answer or the plan took it up
    once more (`replaced` then holds its earlier state); the same outcome again, as a
    resumed workflow returns it, changes nothing."""
    by_key = {str(r.get("key")): r for r in before}
    again = taken_up(before)
    settled: list[str] = []
    for r in new:
        k = str(r.get("key"))
        old = by_key.get(k)
        if old is None or state(old) == "failed":
            by_key[k] = r
        elif {f: v for f, v in old.items() if f != "replaced"} == r:
            continue
        elif k in again:
            by_key[k] = {**r, "replaced": state(old)}
        else:
            settled.append(k)
    return list(by_key.values()), sorted(settled)


def once(records: Records, unverified: Records) -> tuple[Records, Records]:
    """One record per key, the first, naming the other surveys that made it in `also`; a
    finding not verified that another survey's verifier judged is that one's."""
    first: dict[str, dict[str, Any]] = {}
    for r in [*records, *unverified]:
        k = key(r)
        origin = r.get("origin")
        if k not in first:
            first[k] = dict(r)
        elif origin is not None and origin != first[k].get("origin"):
            others = cast("list[Any]", first[k].get("also") or [])
            first[k]["also"] = others if origin in others else [*others, origin]
    judged = {key(r) for r in records}
    return (
        [first[k] for k in dict.fromkeys(key(r) for r in records)],
        [first[k] for k in dict.fromkeys(key(r) for r in unverified) if k not in judged],
    )


def _kept(before: Records, surveyed: list[str] | None) -> Records:
    """What a survey's result leaves of the records so far: the sweep's, and, if it names
    the surveys that answered, those of every other survey."""
    return [
        r
        for r in before
        if str(r.get("origin") or "").startswith("sweep:")
        or (surveyed is not None and r.get("origin") not in surveyed)
    ]


def main(run: Path, output: Path, scanner: Sequence[str] = SCANNER) -> int:
    text = output.read_text(encoding="utf-8")
    if secret(text, str(output), scanner):
        print(f"{output}: nothing written; ask the agent again without the secret", file=sys.stderr)
        return 1
    try:
        whole: object = json.loads(text)
    except ValueError:
        whole = None
    whole = cast("dict[str, Any]", whole) if isinstance(whole, dict) else {}
    result: object = whole.get("result")
    result = cast("dict[str, Any]", result) if isinstance(result, dict) else {}
    findings, outcomes = _objects(result.get("records")), _objects(result.get("outcomes"))
    if findings is not None:
        # The sweep's verdicts join the records; a survey's result replaces what its
        # surveys found before, nothing else. What stays comes first: one record per key
        swept = result.get("sweep") is True
        names = result.get("surveyed")
        surveyed = [str(n) for n in cast("list[Any]", names)] if isinstance(names, list) else None
        judged, waiting = _read(run / "findings.jsonl"), _read(run / "unverified.jsonl")
        if not swept:
            judged, waiting = _kept(judged, surveyed), _kept(waiting, surveyed)
        found, left = once(
            [*judged, *findings], [*waiting, *(_objects(result.get("unverified")) or [])]
        )
        wrote, count = "sweep" if swept else "findings", len(found) - len(judged)
        _write(run / "findings.jsonl", found)
        _write(run / "unverified.jsonl", left)
    elif outcomes is not None:
        records, settled = merged(_read(run / "outcomes.jsonl"), outcomes)
        if settled:
            print(f"already have an outcome: {', '.join(settled)}", file=sys.stderr)
            return 1
        wrote, count = "outcomes", len(outcomes)
        _write(run / "outcomes.jsonl", records)
    else:
        print(f"{output}: no result with records or outcomes", file=sys.stderr)
        return 1
    cost = {"agents": whole.get("agentCount"), "tokens": whole.get("totalTokens")}
    with (run / "workflows.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps({"wrote": wrote, "records": count, **cost}) + "\n")
    print(f"{count} {wrote} written; {cost['agents']} agents, {cost['tokens']} tokens")
    return 0


if __name__ == "__main__":
    build_scanner()
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
