"""The code lens's deterministic stages (ADR-008): its inventory follows the modules in the
repository, its hints point at places, and triage takes a code finding only with what
shows it, as a fix only with the test that shows it wrong."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness import modules, plan, triage


def _tree(root: Path, *files: str) -> Path:
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x = 1\n", encoding="utf-8")
    return root


CODE = "src/enterich"
FILES = (f"{CODE}/__init__.py", f"{CODE}/app.py", f"{CODE}/tools/__init__.py", f"{CODE}/tools/a.py")
SERVICE = {
    "promise": "service",
    "files": [f"{CODE}/__init__.py", f"{CODE}/app.py"],
    "concerns": ["lost-on-the-way", "wrong-outcome"],
    "asks": "Does a path lose what the caller needs?",
}
TOOLS = {**SERVICE, "promise": "tools", "files": [f"{CODE}/tools"]}
TWICE = {
    "promise": "rule-twice",
    "files": [CODE],
    "concerns": ["rule-twice"],
    "asks": "Is one rule written in two places?",
}


def test_a_vocabulary_that_holds_each_module_in_one_group_is_kept(tmp_path: Path) -> None:
    assert modules.unkept([SERVICE, TOOLS, TWICE], _tree(tmp_path, *FILES)) == []


def test_a_module_in_no_group_or_in_two_stops_the_inventory(tmp_path: Path) -> None:
    root = _tree(tmp_path, *FILES, f"{CODE}/log.py")
    twice = {**TOOLS, "promise": "a", "files": [f"{CODE}/tools/a.py"]}
    # A survey across the code holds no module: only the groups count
    assert modules.unkept([SERVICE, TOOLS, TWICE, twice], root) == [
        f"{CODE}/log.py: in no group",
        f"{CODE}/tools/a.py: in 2 groups",
    ]


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        ({**SERVICE, "files": [*SERVICE["files"], f"{CODE}/gone.py"]}, "gone.py doesn't exist"),
        ({**SERVICE, "concerns": []}, "names no concern"),
        ({**SERVICE, "concerns": ["style"]}, "style isn't the lens's"),
        ({**SERVICE, "concerns": ["rule-twice", "wrong-outcome"]}, "across the code and one"),
        ({**SERVICE, "asks": " "}, "says nothing it asks"),
    ],
)
def test_a_record_that_isnt_kept_stops_the_inventory(
    tmp_path: Path, record: dict[str, Any], problem: str
) -> None:
    found = modules.unkept([record, TOOLS, TWICE], _tree(tmp_path, *FILES))
    assert any(problem in p for p in found), found


def test_the_repositorys_vocabulary_holds_each_of_its_modules_in_one_group() -> None:
    assert modules.unkept(modules.vocabulary()) == []


def test_a_change_touches_its_group_and_the_surveys_across_the_code() -> None:
    records = [SERVICE, TOOLS, TWICE]
    assert modules.touched(records, [f"{CODE}/app.py"]) == ["rule-twice", "service"]
    assert modules.touched(records, [f"{CODE}/tools/a.py"]) == ["rule-twice", "tools"]
    # A change outside the code's Python files touches no survey
    assert modules.touched(records, ["docs/guides/a.md", f"{CODE}/py.typed"]) == []


def test_a_literal_two_modules_share_is_a_hint() -> None:
    sources = {
        "a.py": 'LIMIT = 1_000_000_000\nWHY = "party needs party_type here"\n',
        "b.py": 'CAP = 1_000_000_000\nWHY = "party needs party_type here"\nN = 7\n',
        "c.py": "X = 7\n",
    }
    assert modules.shared_literals(sources, length=20, size=100) == [
        {"literal": "'party needs party_type here'", "places": ["a.py:2", "b.py:2"]},
        {"literal": "1000000000", "places": ["a.py:1", "b.py:1"]},
    ]


def test_a_docstring_an_f_string_or_a_casts_type_is_no_hint() -> None:
    text = (
        '"""A docstring long enough to count as a literal."""\n'
        "from typing import cast\n"
        "def f(x):\n"
        '    """Another docstring long enough to count."""\n'
        '    return cast("list[dict[str, Any]]", f"{x} a long enough f-string part")\n'
    )
    assert modules.shared_literals({"a.py": text, "b.py": text}, length=20, size=100) == []


def test_lines_the_tests_never_ran_are_a_hint() -> None:
    report: dict[str, Any] = {
        "files": {
            f"{CODE}/app.py": {
                "missing_lines": [3, 4, 5, 9],
                "missing_branches": [[9, 10], [12, 14]],
            },
            f"{CODE}/log.py": {"missing_lines": [], "missing_branches": []},
        }
    }
    assert modules.uncovered(report, [f"{CODE}/app.py", f"{CODE}/log.py"]) == {
        f"{CODE}/app.py": "3-5, 9; branches at 12"
    }


def test_the_code_inventory_writes_each_record_with_its_hints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The coverage run is the tests themselves; here it found nothing untested
    def nothing_untested(root: Path) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(modules, "_coverage", nothing_untested)
    assert modules.main(tmp_path) == 0
    written = [json.loads(line) for line in (tmp_path / "modules.jsonl").read_text().splitlines()]
    assert [r["promise"] for r in written] == [r["promise"] for r in modules.vocabulary()]
    across = [r for r in written if "rule-twice" in r["concerns"]]
    assert across
    assert all("shared_literals" in r["hints"] for r in across)
    groups = [r for r in written if not set(r["concerns"]) & set(modules.ACROSS)]
    assert all(set(r["hints"]) == {"complex", "untested"} for r in groups)
    assert json.loads(capsys.readouterr().out) == {"records": len(written)}


def test_a_code_vocabulary_that_isnt_kept_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(modules, "vocabulary", lambda: [SERVICE])
    assert modules.main(tmp_path / "run") == 1
    assert not (tmp_path / "run").exists()


# The code lens's findings in triage and the plan

LOST: dict[str, Any] = {
    "kind": "lost-on-the-way",
    "promise": "operations-core",
    "location": "src/enterich/tools/__init__.py:_write_text",
    "requirement": "REQ-001-PRS-F015",
    "mutants": [],
    "claim": "The last fallback drops the warning that the comment is missing",
    "evidence": "__init__.py:356 builds the result with only its own note",
    "proposal": "Keep the warnings; test with a failing comment and an oversized field",
    "origin": "module:operations-core",
    "verdict": {
        "confirmed": True,
        "class": "fix",
        "pattern": None,
        "test_files": ["tests/unit/test_tools.py"],
        "reproduction": "a failing comment and a 200,000-character remarks: warnings [note]",
        "reason": "ran the case against the fake",
    },
}


def test_a_code_run_is_in_its_directorys_name() -> None:
    assert triage.lens(Path("harness/runs/2026-11-19-code")) == "code"
    assert triage.LENSES["code"] == set(modules.CONCERNS)
    assert triage.MODULES == modules.MODULES


def test_a_code_findings_key_names_its_survey_and_place() -> None:
    assert triage.key(LOST) == (
        "lost-on-the-way:operations-core:src/enterich/tools/__init__.py:_write_text"
    )


def test_a_complete_code_finding_can_be_triaged() -> None:
    assert triage.check(LOST, promises={"operations-core"}) == []


@pytest.mark.parametrize(
    ("verdict", "problem"),
    [
        # Confirmed only with both sides shown
        ({"reproduction": None}, "reproduction"),
        # A fix only with the test that shows it wrong; a restructure is a proposal
        ({"test_files": []}, "test_files missing"),
    ],
)
def test_a_code_finding_without_what_shows_it_is_refused(
    verdict: dict[str, Any], problem: str
) -> None:
    record = {**LOST, "verdict": {**LOST["verdict"], **verdict}}
    assert any(problem in p for p in triage.check(record, promises={"operations-core"}))


def test_a_restructure_without_a_test_is_a_proposal() -> None:
    twice: dict[str, Any] = {
        **LOST,
        "kind": "rule-twice",
        "promise": "rule-twice",
        "verdict": {**LOST["verdict"], "class": "proposal", "test_files": []},
    }
    assert triage.check(twice, promises={"rule-twice"}) == []


def test_a_code_runs_branches_are_named_after_its_lens() -> None:
    fix = {**LOST, "key": triage.key(LOST), "slug": triage.slug(LOST), "ratchet": None}
    [group] = plan.groups([fix], [], lens="code")
    assert group["branch"].startswith("auto/code-")
