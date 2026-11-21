"""The tests lens's sweep (ADR-008): a survey misses things, so a class of gap one survey
found is looked for in every survivor. For each confirmed mutant gap, the sweep takes the
project's own functions and classes whose call (or definition) its mutants change, and finds
the survivors left to agents that change the same one and that no finding names. It writes
them by function to `sweep.jsonl`, as findings without a verdict: the workflow's verifiers
judge them, and `record.py` adds their verdicts to `findings.jsonl` for triage. A call of
Python or a library, such as a dict's `get`, is no class and isn't followed.
Deterministic; the agents' records are data here, never instructions.

    uv run python harness/sweep.py harness/runs/<date>-tests
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any, cast

try:
    from harness import project
    from harness.jsonl import read as _records
    from harness.triage import key
except ModuleNotFoundError:  # run as a script: harness/ is the path's first entry
    import project  # type: ignore[import-not-found, no-redef]
    from jsonl import read as _records  # type: ignore[import-not-found, no-redef]
    from triage import key  # type: ignore[import-not-found, no-redef]

ROOT = project.ROOT
SRC = ROOT / project.SOURCES["code"]

Records = list[dict[str, Any]]


def _parsed(line: str) -> ast.Module | None:
    """One line of a diff as Python: a statement, a definition without its body, or an
    argument or expression cut out of a longer one."""
    text = line.strip()
    for attempt in (text, f"{text} pass", f"({text.rstrip(',')})"):
        try:
            return ast.parse(attempt)
        except SyntaxError:
            continue
    return None


Named = tuple[str, str | None]


def _named(tree: ast.Module) -> dict[Named, list[str]]:
    """Each call and definition in the line by its name and the module or object it is
    called on (None for a plain name or a definition), innermost first."""
    found: dict[Named, list[str]] = {}
    for node in reversed(list(ast.walk(tree))):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                owner = func.value
                held = owner.id if isinstance(owner, ast.Name) else None
                held = owner.attr if isinstance(owner, ast.Attribute) else held
                found.setdefault((func.attr, held or "?"), []).append(ast.dump(node))
            else:
                found.setdefault((ast.unparse(func), None), []).append(ast.dump(node))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.setdefault((node.name, None), []).append(ast.dump(node))
    return found


def _ours(named: Named, own: set[str] | None, modules: set[str] | None) -> bool:
    """A call of the project's own: a name it defines, called plainly or on one of its
    modules, `self`, `cls` or one of its classes; not a library's call of the same name."""
    name, owner = named
    if own is not None and name not in own:
        return False
    if owner is None or modules is None:
        return True
    return owner in modules or owner in {"self", "cls"} or owner in (own or set())


def callee(diff: str, own: set[str] | None = None, modules: set[str] | None = None) -> str | None:
    """The innermost call or definition of the project's own (`own`, `modules`; any, if not
    given) that a mutant of one line changes, or None: a change of an operator, a value or
    several lines has no single call."""
    lines = diff.splitlines()
    old = [line[1:] for line in lines if line.startswith("-")]
    new = [line[1:] for line in lines if line.startswith("+")]
    if len(old) != 1 or len(new) != 1:
        return None
    before, after = _parsed(old[0]), _parsed(new[0])
    if before is None or after is None:
        return None
    was, now = _named(before), _named(after)
    changed = [n for n in was if n in now and was[n] != now[n] and _ours(n, own, modules)]
    return changed[0][0] if changed else None


def own_names(src: Path = SRC) -> set[str]:
    """The functions, methods and classes the project defines."""
    definition = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+(\w+)", re.MULTILINE)
    return {name for path in src.rglob("*.py") for name in definition.findall(path.read_text())}


def module_names(src: Path = SRC) -> set[str]:
    """The project's modules and packages, as a call names one: `drafts.named(…)`."""
    return {p.parent.name if p.name == "__init__.py" else p.stem for p in src.rglob("*.py")}


def location(mutant: str) -> str:
    """A survivor's function as a finding names it: `src/enterich/auth.py:Verifier._verify`."""
    module, _, function = mutant.rpartition("__mutmut_")[0].rpartition(".")
    # The package lies in the code's parent directory: src/enterich holds enterich
    path = Path(project.SOURCES["code"]).parent.joinpath(*module.split("."))
    file = path / "__init__.py" if (ROOT / path).is_dir() else path.with_suffix(".py")
    # mutmut's names: x_<function>, or xǁ<class>ǁ<method>
    if function.startswith("xǁ"):
        name = ".".join(function.removeprefix("xǁ").split("ǁ"))
    else:
        name = function.removeprefix("x_")
    return f"{file.as_posix()}:{name}"


def swept(
    survivors: Records,
    findings: Records,
    unverified: Records,
    own: set[str],
    modules: set[str] | None = None,
) -> Records:
    """The survivors no finding names that change a call of the project's own (`own`,
    `modules`) a confirmed mutant gap's mutants change, one candidate per function, each
    with the finding it is like. A survey's finding not yet verified names its survivors
    too; the sweep's own candidates not yet verified don't, so they come again."""
    diffs = {s["id"]: s["diff"] for s in survivors}
    # A candidate of an earlier sweep that no verifier judged is offered again
    waiting = [f for f in unverified if not str(f.get("origin") or "").startswith("sweep:")]
    named = {
        str(m) for f in [*findings, *waiting] for m in cast("list[Any]", f.get("mutants") or [])
    }
    like: dict[str, dict[str, Any]] = {}
    for f in sorted(findings, key=lambda f: str(f.get("mutants"))):
        verdict = cast("dict[str, Any]", f.get("verdict") or {})
        if f.get("kind") != "mutant-gap" or not f.get("mutants") or not verdict.get("confirmed"):
            continue
        for m in f["mutants"]:
            if (name := callee(diffs.get(m, ""), own, modules)) and name not in like:
                like[name] = f
    by_place: dict[str, tuple[dict[str, Any], str, list[str]]] = {}
    for s in survivors:
        name = callee(s["diff"], own, modules)
        if s.get("filter") is not None or s["id"] in named or name is None or name not in like:
            continue
        place = location(s["id"])
        found, _, mutants = by_place.setdefault(place, (like[name], name, []))
        mutants.append(s["id"])
    candidates: Records = []
    for place, (found, name, mutants) in sorted(by_place.items()):
        found_key = key(found)
        candidates.append(
            {
                "kind": "mutant-gap",
                "location": place,
                "requirement": None,
                "mutants": sorted(
                    mutants, key=lambda m: key({"kind": "mutant-gap", "mutants": [m]})
                ),
                "claim": (
                    f"No test notices a changed call of `{name}` here, the class of the "
                    f"confirmed finding {found_key}: {found['claim']}"
                ),
                "evidence": (
                    f"sweep.py: survivors left to agents that change `{name}` as that "
                    f"finding's mutants do ({found['location']}), named in no finding."
                ),
                "proposal": f"As for {found_key}: {found['proposal']}",
                "origin": f"sweep:{found_key}",
                "like": found_key,
            }
        )
    return candidates


def main(run: Path, src: Path = SRC) -> int:
    candidates = swept(
        _records(run / "survivors.jsonl"),
        _records(run / "findings.jsonl"),
        _records(run / "unverified.jsonl"),
        own_names(src),
        module_names(src),
    )
    text = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in candidates)
    (run / "sweep.jsonl").write_text(text, encoding="utf-8")
    mutants = sum(len(c["mutants"]) for c in candidates)
    print(f"{len(candidates)} candidates with {mutants} survivors: sweep.jsonl written")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("run", type=Path, help="the run directory")
    sys.exit(main(parser.parse_args().run))
