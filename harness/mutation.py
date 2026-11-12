"""The tests lens's mutation step (ADR-008): runs mutmut over `src/enterich/` against the
unit and integration tests (`[tool.mutmut]` in pyproject.toml), then writes each surviving
mutant with its diff, and the counts per module, to the run directory given. CPU only;
mutmut keeps its results in `mutants/`, so a second run checks only what changed.

    uv run --group harness python harness/mutation.py harness/runs/<date>-tests [--fresh]
"""

import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTMUT = [sys.executable, "-m", "mutmut"]
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'')
CAST = re.compile(r'cast\("[^"]*",')


def filtered(diff: str) -> str | None:
    """Why a script can judge a survivor without an agent: "message" when only the text of
    strings with a space changed (a message, not a key or name), "cast" when only the type
    text of a `cast()` did; None when it needs an agent."""
    removed = [line[1:] for line in diff.splitlines() if line.startswith("-")]
    added = [line[1:] for line in diff.splitlines() if line.startswith("+")]
    if not removed or len(removed) != len(added):
        return None
    if all(
        CAST.sub("cast(T,", a) == CAST.sub("cast(T,", b)
        for a, b in zip(removed, added, strict=True)
    ):
        return "cast"
    for before, after in zip(removed, added, strict=True):
        if STRING.sub('""', before) != STRING.sub('""', after):
            return None
        changed = [
            old
            for old, new in zip(STRING.findall(before), STRING.findall(after), strict=False)
            if old != new
        ]
        if not changed or not all(" " in old for old in changed):
            return None
    return "message"


def _mutmut(*args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [*MUTMUT, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"mutmut {' '.join(args)} failed: {done.stderr[-2000:]}")
    return done.stdout


def _diff(mutant: str) -> str:
    shown = _mutmut("show", mutant)
    return "\n".join(
        line
        for line in shown.splitlines()
        if line.startswith(("-", "+")) and not line.startswith(("---", "+++"))
    )


def _module(mutant: str) -> str:
    """`enterich.shapes.x_page__mutmut_3` → `enterich.shapes`."""
    head = mutant.split("__mutmut_")[0]
    return ".".join(p for p in head.split(".") if not p.startswith(("x_", "xǁ")))


def main(run: Path, fresh: bool) -> None:
    if fresh:
        shutil.rmtree(ROOT / "mutants", ignore_errors=True)
    workers = str(os.cpu_count() or 2)
    subprocess.run([*MUTMUT, "run", "--max-children", workers], cwd=ROOT, check=True)  # noqa: S603
    statuses: dict[str, str] = {}
    for line in _mutmut("results", "--all", "true").splitlines():
        name, _, status = line.strip().rpartition(": ")
        if name:
            statuses[name] = status
    survivors = sorted(n for n, s in statuses.items() if s == "survived")
    with ThreadPoolExecutor(max_workers=int(workers)) as pool:
        diffs = list(pool.map(_diff, survivors))
    run.mkdir(parents=True, exist_ok=True)
    with (run / "survivors.jsonl").open("w", encoding="utf-8") as out:
        for name, diff in zip(survivors, diffs, strict=True):
            record = {"id": name, "module": _module(name), "filter": filtered(diff), "diff": diff}
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
    per_module: dict[str, Counter[str]] = {}
    for name, status in statuses.items():
        per_module.setdefault(_module(name), Counter())[status] += 1
    summary = {
        "mutants": len(statuses),
        "by_status": dict(Counter(statuses.values())),
        "survivors_filtered": dict(Counter(f for d in diffs if (f := filtered(d)))),
        "by_module": {m: dict(c) for m, c in sorted(per_module.items())},
    }
    (run / "mutation.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("mutants", "by_status")}, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--fresh" in sys.argv[2:])
