"""The docs lens's inventory (ADR-008): the documents the lens reads against the code, each
by what it asks, from `harness/documents.jsonl`, the lens's fixed vocabulary.

Every document that says what Enterich does, the README, the security policy, the guides,
the specs and the architecture, is in exactly one record: one the lens surveys, or one
left out with its reason (`out`). A document in no record or in two, a path that doesn't
exist, or a record that doesn't say what it asks stops the inventory: the vocabulary
follows the documents. With `--since <commit>`, usually where the last run's records were
committed, it also names the files changed since then and the records they touch: a change
to one of a record's documents or to what it is read against. A run after the first
surveys those. Deterministic and read-only; writes to the run directory given.

    uv run python harness/documents.py harness/runs/<date>-docs [--since <commit>]
"""

import json
import sys
from pathlib import Path
from typing import Any, cast

try:
    from harness import surface
    from harness.jsonl import read as _records
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import surface  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = ROOT / "harness" / "documents.jsonl"
# The documents that say what Enterich does; the backlog, the analyses and the changelog
# keep what was true on their day
SCOPE = (
    "README.md",
    "SECURITY.md",
    "docs/guides/*.md",
    "docs/specs/*.md",
    "docs/arc42/*.md",
    "docs/arc42/adr/*.md",
)

Records = list[dict[str, Any]]


def vocabulary() -> Records:
    return _records(DOCUMENTS)


def _under(path: str, entry: str) -> bool:
    return path == entry or path.startswith(entry.rstrip("/") + "/")


def _paths(record: dict[str, Any], field: str) -> list[str]:
    return cast("list[str]", record.get(field) or [])


def in_scope(root: Path = ROOT) -> list[str]:
    return sorted({p.relative_to(root).as_posix() for g in SCOPE for p in root.glob(g)})


def unkept(records: Records, root: Path = ROOT) -> list[str]:
    """What is wrong with the vocabulary; empty when the inventory can be taken."""
    names = [str(r.get("promise")) for r in records]
    problems = [f"{n}: two records of this name" for n in sorted(set(names)) if names.count(n) > 1]
    for r in records:
        problems += [
            f"{r.get('promise')}: {path} doesn't exist"
            for path in _paths(r, "documents") + _paths(r, "against")
            if not (root / path).exists()
        ]
        if "out" in r:
            if not str(r["out"]).strip():
                problems.append(f"{r.get('promise')}: says no reason it is left out")
        elif not str(r.get("asks") or "").strip():
            problems.append(f"{r.get('promise')}: says nothing it asks")
    for path in in_scope(root):
        held = sum(1 for r in records if any(_under(path, d) for d in _paths(r, "documents")))
        if held != 1:
            problems.append(f"{path}: in {f'{held} records' if held else 'no record'}")
    return problems


def touched(records: Records, files: list[str]) -> list[str]:
    """The records surveyed that a change to the files touches: one to a document of
    theirs, or under what they are read against."""
    return sorted(
        str(r["promise"])
        for r in records
        if "out" not in r
        and any(_under(f, p) for f in files for p in _paths(r, "documents") + _paths(r, "against"))
    )


def main(run: Path, root: Path = ROOT, since: str | None = None) -> int:
    records = vocabulary()
    problems = unkept(records, root)
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1
    surveyed = [r for r in records if "out" not in r]
    counts: dict[str, int] = {"documents": len(surveyed)}
    run.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in surveyed)
    (run / "documents.jsonl").write_text(text, encoding="utf-8")
    if since is not None:
        files = surface.changed(since, root)
        hit = touched(records, files)
        commit = surface._git(root, "rev-parse", since).strip()  # pyright: ignore[reportPrivateUsage]
        written = {"commit": commit, "changed": files, "documents": hit}
        (run / "since.json").write_text(json.dumps(written, indent=2) + "\n", encoding="utf-8")
        counts |= {"changed": len(files), "touched": len(hit)}
    print(json.dumps(counts))
    return 0


if __name__ == "__main__":
    arguments = sys.argv[1:]
    after = arguments[arguments.index("--since") + 1] if "--since" in arguments else None
    sys.exit(main(Path(arguments[0]), since=after))
