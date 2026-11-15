"""The improvement pipeline's deterministic stages (ADR-008): the inventory reads the specs
and tests as they are written, triage and the outcomes check refuse a record they can't
trust, and the gate refuses a branch that breaks a rule."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from harness import (
    cleanup,
    gate,
    inventory,
    mutation,
    outcomes,
    plan,
    record,
    surface,
    sweep,
    triage,
)


def test_the_inventory_reads_a_requirements_definition_of_done() -> None:
    by_id = {r.id: r for r in inventory.requirements()}
    tax = by_id["REQ-001-PRS-F022"]
    assert (tax.spec, tax.title) == ("req-001-core.md", "Tax summary")
    # The DoD's items, without its Verification and Evidence lines
    assert len(tax.dod) == 7
    assert not any(item.startswith(("Verification", "Evidence")) for item in tax.dod)


def test_the_inventory_finds_a_tests_own_and_its_sections_ids() -> None:
    by_id = {t.id: t for t in inventory.tests()}
    cut = by_id["tests/integration/test_bank_and_cash.py::test_a_lists_long_texts_are_cut_to_500"]
    assert cut.ids == ["REQ-001-PRS-NF003"]
    # Its section comment and the module's docstring
    assert "REQ-007-PRS-F002" in cut.section_ids


SECTIONS = [
    "# The duplicate match (REQ-007-PRS-F006,",  # 1
    "# REQ-001-PRS-F005)",  # 2
    "",  # 3
    "",  # 4
    "def test_a() -> None: ...",  # 5
    "",  # 6
    "# 100.005 is saved as 100.0 (REQ-001-PRS-F008)",  # 7
    "@pytest.mark.parametrize('amount', [1])",  # 8
    "def test_b(amount: float) -> None: ...",  # 9
    "",  # 10
    "# update_draft_payment_entry",  # 11
    "",  # 12
    "def test_c() -> None: ...",  # 13
]


@pytest.mark.parametrize(
    ("before", "ids"),
    [
        # Every line of a heading's comment block
        (5, ["REQ-001-PRS-F005", "REQ-007-PRS-F006"]),
        # A comment on the line below it is no heading
        (8, ["REQ-001-PRS-F005", "REQ-007-PRS-F006"]),
        # A heading citing nothing starts a section citing nothing
        (13, []),
    ],
)
def test_a_section_is_the_heading_above_with_all_its_lines(before: int, ids: list[str]) -> None:
    assert inventory.section_ids(SECTIONS, before) == ids


def test_a_heading_citing_nothing_ends_the_section_before_it() -> None:
    """In the journal entry's tests, the update's follow the create's rounding."""
    path = inventory.ROOT / "tests" / "integration" / "test_record_to_report_drafts.py"
    lines = path.read_text().splitlines()
    update = next(
        i for i, line in enumerate(lines, 1) if "def test_an_update_sends_exactly" in line
    )
    assert inventory.section_ids(lines, update) == []


def test_every_id_a_test_cites_is_in_a_spec() -> None:
    known = {r.id for r in inventory.requirements()}
    cited = {i for t in inventory.tests() for i in (*t.ids, *t.section_ids)}
    assert cited <= known


def test_the_inventory_leaves_out_the_harness_tests() -> None:
    """They cite requirement IDs as data, not as what they check."""
    assert not any(t.id.startswith("tests/repo/test_harness.py") for t in inventory.tests())


MUTANT = "enterich.shapes.x_to_text__mutmut_6"
MUTANT_ELSEWHERE = "enterich.log.x_line__mutmut_3"
FINDING: dict[str, Any] = {
    "kind": "mutant-gap",
    "location": "src/enterich/shapes.py:to_text",
    "requirement": "REQ-001-PRS-NF003",
    "mutants": [MUTANT, "enterich.shapes.x_to_text__mutmut_12"],
    "claim": "No test notices non-ASCII text escaped",
    "evidence": "mutant to_text_6 survives",
    "proposal": "A result with umlauts keeps them and counts them once",
    "verdict": {"confirmed": True, "class": "fix", "reason": "reproduced"},
}
DOD_GAP: dict[str, Any] = {
    **FINDING,
    "kind": "dod-gap",
    "location": "req-001-core.md#REQ-001-PRS-NF003 item 2",
    "mutants": [],
}


def test_a_complete_record_can_be_triaged() -> None:
    assert triage.check(FINDING) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"kind": "opinion"}, "kind 'opinion'"),
        ({"claim": None}, "claim missing"),
        ({"mutants": []}, "mutants missing"),
        ({"mutants": ["to_text_6"]}, "mutants missing"),
        ({"verdict": {"confirmed": "yes", "class": "fix", "reason": "r"}}, "not a boolean"),
        ({"verdict": {"confirmed": True, "class": "merge", "reason": "r"}}, "verdict.class"),
        ({"verdict": None}, "verdict missing"),
    ],
)
def test_a_record_with_a_wrong_field_is_refused(change: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in triage.check({**FINDING, **change}))


def test_a_mutant_gaps_key_is_its_lowest_mutant() -> None:
    """Two gaps in one function are two findings; a suppression names one of them."""
    assert triage.key(FINDING) == f"mutant-gap:{MUTANT}"
    assert triage.key(DOD_GAP) == "dod-gap:req-001-core.md#REQ-001-PRS-NF003 item 2"


def _write(path: Path, records: list[dict[str, Any]]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def _triage(run: Path, records: list[dict[str, Any]], **lists: list[dict[str, Any]]) -> int:
    _write(run / "findings.jsonl", records)
    suppressions = _write(run / "suppressions.jsonl", lists.get("suppressions", []))
    patterns = _write(run / "patterns.jsonl", lists.get("patterns", []))
    return triage.main(run, suppressions=suppressions, backlog=run / "backlog", patterns=patterns)


def test_triage_writes_no_report_from_a_bad_record(tmp_path: Path) -> None:
    assert _triage(tmp_path, [FINDING, {**DOD_GAP, "kind": "opinion"}]) == 1
    assert not (tmp_path / "report.md").exists()


def test_triage_writes_no_report_from_two_records_with_one_key(tmp_path: Path) -> None:
    other = {**FINDING, "claim": "Another gap", "mutants": [MUTANT]}
    assert _triage(tmp_path, [FINDING, other]) == 1
    assert not (tmp_path / "report.md").exists()


def test_triage_reports_confirmed_findings_by_class(tmp_path: Path) -> None:
    refuted = {**DOD_GAP, "verdict": {**FINDING["verdict"], "confirmed": False}}
    assert _triage(tmp_path, [FINDING, refuted]) == 0
    report = (tmp_path / "report.md").read_text()
    assert "| all | 2 | 1 |" in report
    assert "## Fix (1)" in report
    assert "## Proposal (0)" in report


def test_a_quoted_filter_list_reads_as_no_wiki_link_in_the_report(tmp_path: Path) -> None:
    quoted = {**FINDING, "proposal": 'Assert filters == [["company", "=", COMPANY]]'}
    assert _triage(tmp_path, [quoted]) == 0
    assert "[[" not in (tmp_path / "report.md").read_text()


def test_triage_hands_the_fix_stage_each_fix_with_its_mutants(tmp_path: Path) -> None:
    survivor = {"id": MUTANT, "module": "enterich.shapes", "filter": None, "diff": "-a\n+b"}
    _write(tmp_path / "survivors.jsonl", [survivor])
    proposal = {**DOD_GAP, "verdict": {**FINDING["verdict"], "class": "proposal"}}
    assert _triage(tmp_path, [FINDING, proposal]) == 0
    fixes = [json.loads(line) for line in (tmp_path / "fixes.jsonl").read_text().splitlines()]
    assert [(f["key"], f["slug"]) for f in fixes] == [(triage.key(FINDING), "shapes-to-text-6")]
    # A mutant gone from survivors.jsonl has no diff to hand over
    assert fixes[0]["diffs"] == {MUTANT: "-a\n+b"}


def test_a_record_cant_name_its_own_key_or_slug(tmp_path: Path) -> None:
    """An agent's record is data: what the fix stage is handed is computed from it."""
    forged = {**FINDING, "key": "mutant-gap:another", "slug": "../main", "ratchet": "x"}
    assert _triage(tmp_path, [forged]) == 0
    [fix] = _lines(tmp_path / "fixes.jsonl")
    assert (fix["key"], fix["slug"], fix["ratchet"]) == (
        triage.key(FINDING),
        triage.slug(FINDING),
        None,
    )


def test_a_definition_of_done_gaps_slug_names_its_item() -> None:
    assert triage.slug(DOD_GAP) == "req-001-prs-nf003-item-2"


def test_a_finding_is_tracked_while_its_backlog_item_is_open(tmp_path: Path) -> None:
    """A suppression naming a backlog item lapses once the item is archived."""
    (tmp_path / "backlog" / "archive").mkdir(parents=True)
    (tmp_path / "backlog" / "item-007-open.md").write_text("# Open\n")
    (tmp_path / "backlog" / "archive" / "item-003-done.md").write_text("# Done\n")
    suppressions = [
        {"key": triage.key(FINDING), "reason": "planned", "backlog": "item-007-open.md"},
        {"key": triage.key(DOD_GAP), "reason": "was planned", "backlog": "item-003-done.md"},
    ]
    assert _triage(tmp_path, [FINDING, DOD_GAP], suppressions=suppressions) == 0
    report = (tmp_path / "report.md").read_text()
    assert "Suppressed: 0. Tracked in the backlog: 1." in report
    assert "## Fix (1)" in report
    assert "item 2" in report


def test_a_suppression_without_a_backlog_item_drops_the_finding(tmp_path: Path) -> None:
    suppressions = [{"key": triage.key(FINDING), "reason": "noise"}]
    assert _triage(tmp_path, [FINDING, DOD_GAP], suppressions=suppressions) == 0
    report = (tmp_path / "report.md").read_text()
    assert "Suppressed: 1. Tracked in the backlog: 0." in report
    assert "## Fix (1)" in report


AT_THE_LIMIT = "limit-not-at-boundary"
PATTERN = {"pattern": AT_THE_LIMIT, "means": "A limit is tested past its boundary, never at it"}


def _with_pattern(record: dict[str, Any], pattern: str | None) -> dict[str, Any]:
    return {**record, "verdict": {**record["verdict"], "pattern": pattern}}


def _lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_a_verdicts_pattern_is_from_the_vocabulary() -> None:
    known = {AT_THE_LIMIT}
    assert triage.check(_with_pattern(FINDING, AT_THE_LIMIT), known) == []
    assert triage.check(_with_pattern(FINDING, None), known) == []
    hunch = triage.check(_with_pattern(FINDING, "a-hunch"), known)
    assert hunch == ["verdict.pattern 'a-hunch'"]


def test_the_pattern_vocabulary_is_a_slug_and_its_meaning_per_line() -> None:
    known = triage.vocabulary()
    assert known
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) for name in known)
    assert all(means.strip() for means in known.values())


def test_a_vocabulary_naming_a_pattern_twice_is_refused(tmp_path: Path) -> None:
    twice = _write(tmp_path / "patterns.jsonl", [PATTERN, PATTERN])
    with pytest.raises(ValueError, match=AT_THE_LIMIT):
        triage.vocabulary(twice)


def _third(location: str, mutant: str) -> dict[str, Any]:
    return _with_pattern({**FINDING, "location": location, "mutants": [mutant]}, AT_THE_LIMIT)


def test_a_pattern_in_three_findings_across_two_files_becomes_a_ratchet(tmp_path: Path) -> None:
    """One generic test closes a class; its findings follow it on the ratchet's branch."""
    here = _with_pattern(FINDING, AT_THE_LIMIT)
    there = _with_pattern(DOD_GAP, AT_THE_LIMIT)
    third = _third("src/enterich/log.py:line", MUTANT_ELSEWHERE)
    alone = {
        **FINDING,
        "location": "src/enterich/log.py:cut",
        "mutants": ["enterich.log.x_cut__mutmut_1"],
    }
    assert _triage(tmp_path, [here, there, third, alone], patterns=[PATTERN]) == 0
    shared = [triage.key(here), triage.key(there), triage.key(third)]
    assert _lines(tmp_path / "ratchets.jsonl") == [
        {
            "key": f"ratchet:{AT_THE_LIMIT}",
            "slug": f"ratchet-{AT_THE_LIMIT}",
            **PATTERN,
            "findings": sorted(shared),
        }
    ]
    marked = {f["key"]: f["ratchet"] for f in _lines(tmp_path / "fixes.jsonl")}
    assert marked == {**dict.fromkeys(shared, AT_THE_LIMIT), triage.key(alone): None}
    report = (tmp_path / "report.md").read_text()
    assert "## Ratchet (1)" in report
    assert f"| `{AT_THE_LIMIT}` | 3 |" in report


def _ratchets_of(run: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert _triage(run, records, patterns=[PATTERN]) == 0
    assert {f["ratchet"] for f in _lines(run / "fixes.jsonl")} == {None}
    return _lines(run / "ratchets.jsonl")


def test_two_findings_are_no_class(tmp_path: Path) -> None:
    """Two tests close them; the third run's ratchet came from two neighbours."""
    pair = [_with_pattern(FINDING, AT_THE_LIMIT), _with_pattern(DOD_GAP, AT_THE_LIMIT)]
    assert _ratchets_of(tmp_path, pair) == []


def test_three_findings_in_one_file_are_no_class(tmp_path: Path) -> None:
    neighbours = [
        _with_pattern(FINDING, AT_THE_LIMIT),
        _third("src/enterich/shapes.py:page", "enterich.shapes.x_page__mutmut_9"),
        _third("src/enterich/shapes.py:cut", "enterich.shapes.x_cut__mutmut_2"),
    ]
    assert _ratchets_of(tmp_path, neighbours) == []


def test_a_pattern_found_in_one_place_is_no_ratchet(tmp_path: Path) -> None:
    refuted = _with_pattern(DOD_GAP, AT_THE_LIMIT)
    refuted["verdict"]["confirmed"] = False
    assert (
        _triage(tmp_path, [_with_pattern(FINDING, AT_THE_LIMIT), refuted], patterns=[PATTERN]) == 0
    )
    assert _lines(tmp_path / "ratchets.jsonl") == []
    assert [f["ratchet"] for f in _lines(tmp_path / "fixes.jsonl")] == [None]
    assert "## Ratchet (0)" in (tmp_path / "report.md").read_text()


def test_triage_writes_no_report_from_a_pattern_outside_the_vocabulary(tmp_path: Path) -> None:
    assert _triage(tmp_path, [_with_pattern(FINDING, "a-hunch")], patterns=[PATTERN]) == 1
    assert not (tmp_path / "report.md").exists()


SOURCE = """
class Client:
    async def send(self, path, limit):
        log.info("call failed")
        log.warning("call failed", extra={"event name": path})
        if limit > 10:
            raise ErpnextError("ERPNext's answer exceeded 10 MiB.")
        if not path:
            raise Refusal(
                "The draft is gone. "
                f"Read it again with {path}."
            )
        rows = cast("list[Any]", value)
        headers = {"authorization": f"token {key}:{secret}"}
        stamp = now.strftime("%Y-%m-%d %H:%M")
        await respond(send, 413, {"error": "request body over 1 MiB"})
        drafts.fetch(context, "Payment Entry", name, what="the payment entry")
        raise drafts.refuse(matches, kind="payment entry")


def warnings(rows):
    found = []
    found.append("The rate is missing. Give the rate.")
    parser.error("no such option")
    return found


def twice(name):
    if not name:
        raise ValueError("not a name")
    return label("not a name")
"""


@pytest.mark.parametrize(
    ("function", "old", "new", "kind"),
    [
        # The wording of an error that is raised, or of a log message: noise
        (
            "Client.send",
            'raise ErpnextError("ERPNext\'s answer exceeded 10 MiB.")',
            'raise ErpnextError("XXERPNext\'s answer exceeded 10 MiB.XX")',
            "message",
        ),
        ("Client.send", '"The draft is gone. "', '"THE DRAFT IS GONE. "', "message"),
        (
            "Client.send",
            'f"Read it again with {path}."',
            'f"read it again with {path}."',
            "message",
        ),
        ("Client.send", 'log.info("call failed")', 'log.info("XXcall failedXX")', "message"),
        # Type text in cast() is never checked at runtime: equivalent
        (
            "Client.send",
            'rows = cast("list[Any]", value)',
            'rows = cast("LIST[ANY]", value)',
            "cast",
        ),
        # A string that goes anywhere else is a value, whatever it looks like: a log
        # record's field, a header, a date's format, an answer's body, a name, a text that
        # another function puts into a refusal or a result
        (
            "Client.send",
            'log.warning("call failed", extra={"event name": path})',
            'log.warning("call failed", extra={"XXevent nameXX": path})',
            None,
        ),
        (
            "Client.send",
            'headers = {"authorization": f"token {key}:{secret}"}',
            'headers = {"authorization": f"XXtoken {key}:{secret}XX"}',
            None,
        ),
        (
            "Client.send",
            'stamp = now.strftime("%Y-%m-%d %H:%M")',
            'stamp = now.strftime("%y-%m-%d %h:%m")',
            None,
        ),
        (
            "Client.send",
            'await respond(send, 413, {"error": "request body over 1 MiB"})',
            'await respond(send, 413, {"error": "REQUEST BODY OVER 1 MIB"})',
            None,
        ),
        (
            "Client.send",
            'drafts.fetch(context, "Payment Entry", name, what="the payment entry")',
            'drafts.fetch(context, "Payment Entry", name, what="THE PAYMENT ENTRY")',
            None,
        ),
        (
            "Client.send",
            'raise drafts.refuse(matches, kind="payment entry")',
            'raise drafts.refuse(matches, kind="XXpayment entryXX")',
            None,
        ),
        (
            "warnings",
            'found.append("The rate is missing. Give the rate.")',
            'found.append("XXThe rate is missing. Give the rate.XX")',
            None,
        ),
        # A call that only sounds like a logger's
        ("warnings", 'parser.error("no such option")', 'parser.error("NO SUCH OPTION")', None),
        # A line that reads the same in two places counts by both
        ("twice", 'raise ValueError("not a name")', 'raise ValueError("NOT A NAME")', "message"),
        ("twice", 'return label("not a name")', 'return label("NOT A NAME")', None),
        # A string without a space is a key or a code, in an error too
        (
            "twice",
            'raise ValueError("invalid_token")',
            'raise ValueError("XXinvalid_tokenXX")',
            None,
        ),
        # Code changed, with or without a message
        ("Client.send", "if limit > 10:", "if limit >= 10:", None),
        (
            "Client.send",
            'raise ErpnextError("ERPNext\'s answer exceeded 10 MiB.") if n > 1 else None',
            'raise ErpnextError("erpnext\'s answer exceeded 10 mib.") if n >= 1 else None',
            None,
        ),
    ],
)
def test_survivors_a_script_can_judge_are_filtered(
    function: str, old: str, new: str, kind: str | None
) -> None:
    """ADR-008: only what no caller can observe is left out of the agents' survey. What a
    string is follows from where the function's source sends it."""
    messages = mutation.message_lines(SOURCE, function)
    assert mutation.filtered(f"-    {old}\n+    {new}", messages) == kind


def test_a_survivor_whose_source_cant_be_read_is_left_to_the_agents(tmp_path: Path) -> None:
    diff = '-    raise ValueError("not a name")\n+    raise ValueError("NOT A NAME")'
    assert mutation.filtered(diff) is None
    assert mutation.messages_of("enterich.gone.x_twice__mutmut_1", tmp_path) == {}
    module = tmp_path / "src" / "enterich" / "gone.py"
    module.parent.mkdir(parents=True)
    module.write_text(SOURCE)
    messages = mutation.messages_of("enterich.gone.x_twice__mutmut_1", tmp_path)
    assert mutation.filtered(diff, messages) == "message"


TESTS_ONLY = ["tests/unit/test_shapes.py"]


def test_a_fix_branch_with_a_test_first_passes_the_gate() -> None:
    subjects = ["test: a page of exactly limit records has no more", "fix: has_more at the limit"]
    paths = [*TESTS_ONLY, "src/enterich/shapes.py", "CHANGELOG.md"]
    assert gate.problems("auto/tests-page-limit", subjects, paths) == []


def test_a_survey_branch_of_several_findings_passes_the_gate() -> None:
    subjects = ["test: a", "test: b", "fix: b", "test: c", "refactor: c"]
    assert gate.problems("auto/tests-req-001-core", subjects, TESTS_ONLY) == []


@pytest.mark.parametrize(
    "subjects",
    [["test: a", "fix: a", "fix: b"], ["test: a", "chore: tidy"], ["test: a", "docs: d"]],
)
def test_the_gate_refuses_a_change_not_right_after_its_test(subjects: list[str]) -> None:
    assert any("right after" in p for p in gate.problems("auto/x", subjects, TESTS_ONLY))


@pytest.mark.parametrize(
    ("branch", "subjects", "paths", "problem"),
    [
        ("fix/page-limit", ["test: t"], TESTS_ONLY, "not an auto/ branch"),
        ("auto/x", [], [], "no commits"),
        ("auto/x", ["fix: f", "test: t"], TESTS_ONLY, "test: first"),
        ("auto/x", ["test: t", "Fix the page"], TESTS_ONLY, "not a Conventional Commit"),
        ("auto/x", ["test: t"], [*TESTS_ONLY, "docs/specs/req-001-core.md"], "docs/specs/"),
        ("auto/x", ["test: t"], ["docs/arc42/adr/ADR-008-improvement-pipeline.md"], "adr"),
        ("auto/x", ["test: t"], ["AGENTS.md"], "AGENTS.md"),
        ("auto/x", ["test: t"], [".github/workflows/ci.yml"], ".github/"),
        ("auto/x", ["test: t"], ["pyproject.toml", "uv.lock"], "pyproject.toml"),
        ("auto/x", ["test: t"], ["tests/snapshots/test_tools.ambr"], "tests/snapshots/"),
        ("auto/x", ["test: t"], ["harness/triage.py"], "harness/"),
    ],
)
def test_the_gate_refuses_what_adr_008_forbids(
    branch: str, subjects: list[str], paths: list[str], problem: str
) -> None:
    assert any(problem in p for p in gate.problems(branch, subjects, paths))


def test_the_gate_refuses_a_commit_no_review_accepted() -> None:
    """A rejected fix is dropped from its branch by hand; a commit of an agent that died,
    or that answered "refuted" and committed anyway, was never reviewed at all."""
    subjects = ["test: a", "test: b"]
    assert gate.problems("auto/x", subjects, TESTS_ONLY, unreviewed=[]) == []
    found = gate.problems("auto/x", subjects, TESTS_ONLY, unreviewed=["test: b"])
    assert found == ["'test: b' is no commit of a fix a review accepted"]


def test_the_gate_lets_through_only_the_commits_of_accepted_fixes() -> None:
    commits = [("a" * 40, "test: a"), ("b" * 40, "test: b"), ("c" * 40, "test: c")]
    # An agent may give the start of a hash
    assert gate.unreviewed(commits, ["a" * 12, "c" * 40], {}) == ["test: b"]
    assert gate.unreviewed(commits, [], {}) == ["test: a", "test: b", "test: c"]


def test_an_accepted_commit_keeps_its_place_after_a_rejected_one_is_dropped() -> None:
    """Dropping a commit gives the ones after it new hashes, not new diffs."""
    commits = [("a" * 40, "test: a"), ("d" * 40, "test: c")]
    same_diff = {"c" * 40: "p3", "d" * 40: "p3", "a" * 40: "p1"}
    assert gate.unreviewed(commits, ["a" * 40, "c" * 40], same_diff) == []
    assert gate.unreviewed(commits, ["a" * 40, "c" * 40], {**same_diff, "d" * 40: "p4"}) == [
        "test: c"
    ]


@pytest.mark.parametrize(
    "path",
    [
        "ruff.toml",
        "tests/.ruff.toml",
        "pytest.ini",
        "tests/pytest.ini",
        "tox.ini",
        "setup.cfg",
        "pyrightconfig.json",
        ".mdformat.toml",
        "lychee.toml",
        "scripts/check-links.sh",
        # Among the tests and the code too, where the lens does change files
        "tests/pytest.toml",
        "tests/unit/pyproject.toml",
        "tests/integration/.mdformat.toml",
        "tests/.lycheeignore",
        "src/enterich/CLAUDE.md",
        "tests/AGENTS.md",
    ],
)
def test_the_gate_refuses_a_change_to_what_configures_its_checks(path: str) -> None:
    """A branch could otherwise weaken the checks it is judged by, or instruct its agents."""
    found = gate.problems("auto/x", ["test: t"], [path])
    assert any(path in p and "outside what the pipeline may change" in p for p in found)


@pytest.mark.parametrize(
    "path", ["README.md", "docs/guides/development.md", "conftest.py", ".gitignore", "src/x.py"]
)
def test_the_gate_refuses_what_the_tests_lens_doesnt_change(path: str) -> None:
    """A list of what is forbidden always misses a file; the lens's own list is short."""
    assert gate.problems("auto/x", ["test: t"], [path]) == [
        f"{path} is outside what the tests lens changes (tests/, src/enterich/, CHANGELOG.md)"
    ]


def test_the_gate_lets_through_tests_code_and_the_changelog() -> None:
    paths = ["tests/unit/test_new.py", "tests/fakes/erpnext.py", "src/enterich/shapes.py"]
    assert gate.problems("auto/x", ["test: t", "fix: f"], [*paths, "CHANGELOG.md"]) == []


def test_a_test_commit_changes_only_tests() -> None:
    changes = [
        ("test: a", ["tests/unit/test_a.py"]),
        ("test: b", ["tests/unit/test_b.py", "src/enterich/shapes.py"]),
        ("fix: b", ["src/enterich/shapes.py", "CHANGELOG.md"]),
    ]
    assert gate.beyond_tests(changes) == ["test: b"]
    found = gate.problems("auto/x", ["test: a"], TESTS_ONLY, beyond_tests=["test: a"])
    assert found == ["'test: a' changes more than tests: the code comes in its own commit"]


def test_branches_gated_together_dont_change_the_same_code_or_changelog() -> None:
    """The plan keeps their test files apart; code and the changelog only the gate sees.
    Only a branch that passed holds a path: one that failed blocks no other."""
    mine = ["tests/unit/test_a.py", "src/enterich/shapes.py", "CHANGELOG.md"]
    passed = {
        "auto/tests-b": ["tests/unit/test_a.py", "src/enterich/shapes.py"],
        "auto/tests-c": ["CHANGELOG.md", "src/enterich/shapes.py"],
    }
    assert gate.shared(mine, passed) == {
        "CHANGELOG.md": "auto/tests-c",
        "src/enterich/shapes.py": "auto/tests-b",
    }
    assert gate.shared(mine, {}) == {}
    found = gate.problems("auto/x", ["test: a"], TESTS_ONLY, shared={"CHANGELOG.md": "auto/y"})
    assert found == [
        "CHANGELOG.md is also changed by auto/y: gate this branch after that one is merged"
    ]


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "docs").mkdir()
    (repo / "docs" / "spec.md").write_text("the contract\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "docs: a spec")
    return repo


def test_the_gate_sees_a_forbidden_file_moved_away(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "auto/x")
    (repo / "tests").mkdir()
    _git(repo, "mv", "docs/spec.md", "tests/spec.md")
    _git(repo, "commit", "-q", "-m", "test: move it")
    commit = _git(repo, "rev-parse", "auto/x")
    state = gate.branch_state(repo, "main", commit)
    assert state.paths == ["docs/spec.md", "tests/spec.md"]
    assert state.changes == [("test: move it", ["docs/spec.md", "tests/spec.md"])]


def test_the_gate_reads_a_path_as_it_is_whatever_its_name_holds(tmp_path: Path) -> None:
    """git quotes a name with a space, a tab or a letter outside ASCII; read that way, a
    workflow file of such a name would slip past the list."""
    repo = _repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "auto/x")
    names = [".github/workflows/é.yml", "docs/specs/a b.md", "tests/unit/test_a.py"]
    for name in names:
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text("x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "test: names")
    state = gate.branch_state(repo, "main", _git(repo, "rev-parse", "auto/x"))
    assert state.paths == names
    assert state.changes == [("test: names", names)]
    found = gate.problems("auto/x", ["test: names"], state.paths)
    assert [p.partition(" is outside")[0] for p in found] == names[:2]


def test_a_commit_with_the_same_lines_at_another_depth_is_another_commit(tmp_path: Path) -> None:
    """An assertion moved out of its `if` is another test, though the lines read the same."""
    repo = _repo(tmp_path)
    test = repo / "test_a.py"

    def commit(text: str, branch: str) -> str:
        _git(repo, "switch", "-q", "-c", branch, "main")
        test.write_text(text)
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "test: a")
        return _git(repo, "rev-parse", "HEAD")

    reviewed = commit("def test_a():\n    if x:\n        assert y\n", "auto/a")
    same = commit("def test_a():\n    if x:\n        assert y\n", "auto/b")
    shifted = commit("def test_a():\n    if x:\n      assert y\n", "auto/c")
    ids = gate.patch_ids([reviewed, same, shifted], repo)
    assert ids[reviewed] == ids[same] != ids[shifted]


def test_a_push_that_fails_is_recorded_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate's record of the branch is written either way, and the other branches go on."""
    upstream, clone = _cloned(tmp_path)
    commit = _git(clone, "rev-parse", "HEAD")
    assert gate.pushed(clone, commit, "auto/x") is True
    assert _git(upstream, "rev-parse", "auto/x") == commit
    shutil.rmtree(upstream)
    assert gate.pushed(clone, commit, "auto/y") is False
    assert "auto/y: the push failed" in capsys.readouterr().err


def test_the_gate_reads_the_commit_it_checks_not_where_the_branch_is_now(tmp_path: Path) -> None:
    """The branch may move while the checks run; what is checked is what is pushed."""
    repo = _repo(tmp_path)
    _git(repo, "switch", "-q", "-c", "auto/x")
    (repo / "a.txt").write_text("a")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "test: a")
    checked = _git(repo, "rev-parse", "HEAD")
    (repo / "b.txt").write_text("b")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "test: b")
    state = gate.branch_state(repo, "main", checked)
    assert [subject for _, subject in state.commits] == ["test: a"]
    assert state.paths == ["a.txt"]


def test_no_workflow_names_a_session_or_a_model() -> None:
    """Commit trailers belong to the session that runs a workflow, never to the method."""
    scripts = sorted((gate.ROOT / ".claude" / "workflows").glob("*.js"))
    assert scripts
    for script in scripts:
        text = script.read_text()
        assert "claude.ai/code/session_" not in text, script.name
        assert "Co-Authored-By" not in text, script.name


def test_the_fix_workflow_tells_its_agents_what_the_gate_lets_through() -> None:
    """The prompt's list is written by hand; the gate's is the one that holds."""
    script = (gate.ROOT / ".claude" / "workflows" / "improve-tests-fix.js").read_text()
    [may] = re.findall(r"const MAY_CHANGE = '([^']*)'", script)
    assert re.findall(r"[\w./]+", may.replace(" and ", " ")) == list(gate.ALLOWED)
    assert "tests/snapshots/" in script
    assert "FORBIDDEN =" not in script


SHA = "a" * 40
FIXED: dict[str, Any] = {
    "status": "committed",
    "branch": "auto/tests-shapes",
    "commits": [f"{SHA} test: a result with umlauts keeps them"],
    "tests": ["tests/unit/test_shapes.py::test_umlauts_are_kept"],
    "red": "mutant 6 applied: the count assertion failed",
    "notes": "",
}
REVIEW: dict[str, Any] = {"accept": True, "problems": [], "reason": "red check redone"}
OUTCOME: dict[str, Any] = {
    "key": triage.key(FINDING),
    "slug": "shapes-to-text-6",
    "branch": "auto/tests-shapes",
    "fixed": FIXED,
    "review": REVIEW,
}
NOTHING_COMMITTED: dict[str, Any] = {**FIXED, "commits": [], "tests": []}


def test_a_complete_outcome_passes_its_check() -> None:
    assert outcomes.check(OUTCOME) == []
    assert outcomes.check({**OUTCOME, "fixed": None, "review": None}) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"key": None}, "key missing"),
        ({"branch": "fix/shapes"}, "not an auto/ branch"),
        ({"fixed": {**FIXED, "status": "merged"}}, "fixed.status 'merged'"),
        ({"fixed": {**FIXED, "commits": ["test: no hash"]}}, "fixed.commits"),
        ({"fixed": {**FIXED, "red": None}}, "fixed.red missing"),
        ({"review": {**REVIEW, "accept": "yes"}}, "review.accept not a boolean"),
        ({"review": {**REVIEW, "reason": None}}, "review.reason missing"),
        (
            {"fixed": {**NOTHING_COMMITTED, "status": "refuted"}},
            "a review of a fix that committed nothing",
        ),
    ],
)
def test_an_outcome_with_a_wrong_field_is_refused(change: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in outcomes.check({**OUTCOME, **change}))


@pytest.mark.parametrize(
    ("change", "state"),
    [
        ({}, "accepted"),
        ({"review": {**REVIEW, "accept": False}}, "rejected"),
        # The review agent gave no answer: not accepted either
        ({"review": None}, "unreviewed"),
        ({"fixed": {**NOTHING_COMMITTED, "status": "refuted"}, "review": None}, "refuted"),
        ({"fixed": {**NOTHING_COMMITTED, "status": "proposal"}, "review": None}, "proposal"),
        # The test belongs in a file planned for another branch
        ({"fixed": {**NOTHING_COMMITTED, "status": "elsewhere"}, "review": None}, "elsewhere"),
        # The fix agent gave no answer, or says committed and names no commit
        ({"fixed": None, "review": None}, "failed"),
        ({"fixed": NOTHING_COMMITTED, "review": None}, "failed"),
    ],
)
def test_an_outcome_has_one_state(change: dict[str, Any], state: str) -> None:
    assert outcomes.state({**OUTCOME, **change}) == state


OTHER_KEY = triage.key(DOD_GAP)


def _outcomes(run: Path, records: list[dict[str, Any]], handed: list[str]) -> int:
    _write(run / "fixes.jsonl", [{"key": k} for k in handed])
    _write(run / "outcomes.jsonl", records)
    return outcomes.main(run)


def test_outcomes_counts_the_states_and_lists_the_commits_no_review_accepted(
    tmp_path: Path,
) -> None:
    other = "b" * 40
    rejected = {
        **OUTCOME,
        "key": OTHER_KEY,
        "fixed": {**FIXED, "commits": [f"{other} test: t", f"{'c' * 40} fix: f"]},
        "review": {**REVIEW, "accept": False},
    }
    assert _outcomes(tmp_path, [OUTCOME, rejected], [OUTCOME["key"], OTHER_KEY]) == 0
    summary = json.loads((tmp_path / "outcomes.json").read_text())
    assert summary["fixes"] == 2
    assert summary["states"] == {"accepted": 1, "rejected": 1}
    assert summary["unaccepted"] == {"auto/tests-shapes": [other, "c" * 40]}
    assert summary["missing"] == []
    # The gate lets through only these
    assert summary["accepted"] == {"auto/tests-shapes": [SHA]}


def test_outcomes_names_the_fixes_without_an_outcome(tmp_path: Path) -> None:
    """A fix agent that never ran leaves no record: the run isn't done, not wrong."""
    assert _outcomes(tmp_path, [OUTCOME], [OUTCOME["key"], OTHER_KEY]) == 0
    assert json.loads((tmp_path / "outcomes.json").read_text())["missing"] == [OTHER_KEY]


@pytest.mark.parametrize(
    "records",
    [
        [{**OUTCOME, "branch": "main"}],
        # Two records with one key
        [OUTCOME, OUTCOME],
        # A key triage didn't hand to the fix stage
        [{**OUTCOME, "key": "weak-test:tests/unit/test_x.py::test_y"}],
    ],
)
def test_outcomes_writes_no_counts_from_a_record_it_cant_trust(
    tmp_path: Path, records: list[dict[str, Any]]
) -> None:
    assert _outcomes(tmp_path, records, [OUTCOME["key"]]) == 1
    assert not (tmp_path / "outcomes.json").exists()


def test_outcomes_takes_the_outcome_of_a_ratchet(tmp_path: Path) -> None:
    """A ratchet's generic test is committed and reviewed like a fix."""
    key = f"ratchet:{AT_THE_LIMIT}"
    _write(tmp_path / "ratchets.jsonl", [{"key": key}])
    ratchet = {**OUTCOME, "key": key, "slug": f"ratchet-{AT_THE_LIMIT}"}
    assert _outcomes(tmp_path, [OUTCOME, ratchet], [OUTCOME["key"]]) == 0
    summary = json.loads((tmp_path / "outcomes.json").read_text())
    assert (summary["fixes"], summary["states"]) == (2, {"accepted": 2})


SHAPES, LOG, CONFIG = (f"tests/unit/test_{name}.py" for name in ("shapes", "log", "config"))


@pytest.mark.parametrize(
    ("files", "problems"),
    [
        ([SHAPES], []),
        ([SHAPES, "tests/integration/test_service.py"], []),
        # Records from before verdicts named files
        (None, []),
        (SHAPES, ["verdict.test_files: test modules under tests/"]),
        (["src/enterich/shapes.py"], ["verdict.test_files: test modules under tests/"]),
    ],
)
def test_a_verdict_names_the_test_files_of_its_fix(files: Any, problems: list[str]) -> None:
    record = {**FINDING, "verdict": {**FINDING["verdict"], "test_files": files}}
    assert triage.check(record) == problems


def _fix(name: str, files: list[str] | None, **more: Any) -> dict[str, Any]:
    fix = {"key": f"dod-gap:{name}", "slug": name, "origin": "spec:req-001-core.md"}
    return {**fix, "ratchet": None, "verdict": {"test_files": files}, **more}


def _plan(run: Path, fixes: list[dict[str, Any]], *ratchets: dict[str, Any]) -> list[Any]:
    _write(run / "fixes.jsonl", fixes)
    _write(run / "ratchets.jsonl", list(ratchets))
    assert plan.main(run) == 0
    groups: list[dict[str, Any]] = json.loads((run / "groups.json").read_text())
    return [(g["branch"], g["files"], [f["key"] for f in g["fixes"]]) for g in groups]


def test_fixes_that_share_a_test_file_share_a_branch(tmp_path: Path) -> None:
    """Branches that plan no file in common can't conflict in their tests."""
    fixes = [_fix("a", [SHAPES]), _fix("b", [LOG, SHAPES]), _fix("c", [LOG]), _fix("d", [CONFIG])]
    assert _plan(tmp_path, fixes) == [
        ("auto/tests-unit-config", [CONFIG], ["dod-gap:d"]),
        ("auto/tests-unit-log", [LOG, SHAPES], ["dod-gap:a", "dod-gap:b", "dod-gap:c"]),
    ]


def test_a_ratchets_findings_share_its_branch(tmp_path: Path) -> None:
    """They follow its generic test, whatever files they name."""
    key = f"ratchet:{AT_THE_LIMIT}"
    ratchet = {
        "key": key,
        "slug": f"ratchet-{AT_THE_LIMIT}",
        "findings": ["dod-gap:a", "dod-gap:c"],
    }
    fixes = [
        _fix("a", [SHAPES], ratchet=AT_THE_LIMIT),
        _fix("b", [LOG]),
        _fix("c", [CONFIG], ratchet=AT_THE_LIMIT),
    ]
    assert _plan(tmp_path, fixes, ratchet) == [
        (f"auto/tests-ratchet-{AT_THE_LIMIT}", [CONFIG, SHAPES], ["dod-gap:a", "dod-gap:c"]),
        ("auto/tests-unit-log", [LOG], ["dod-gap:b"]),
    ]
    first = json.loads((tmp_path / "groups.json").read_text())[0]
    assert first["ratchets"] == [{"key": key, "slug": f"ratchet-{AT_THE_LIMIT}"}]
    assert [f["ratchet"] for f in first["fixes"]] == [key, key]
    assert [f["ratchet_done"] for f in first["fixes"]] == [False, False]


def test_a_fix_naming_no_test_file_stays_with_its_survey(tmp_path: Path) -> None:
    """Records from before verdicts named files: one branch per survey, as the runs so far."""
    modules = "mutants:3"
    fixes = [_fix("a", None), _fix("b", None), _fix("c", None, origin=modules)]
    assert _plan(tmp_path, fixes) == [
        ("auto/tests-mutants-3", [], ["dod-gap:c"]),
        ("auto/tests-spec-req-001-core", [], ["dod-gap:a", "dod-gap:b"]),
    ]


def test_two_files_of_one_name_get_two_branches(tmp_path: Path) -> None:
    service = "tests/integration/test_config.py"
    planned = _plan(tmp_path, [_fix("a", [CONFIG]), _fix("b", [service])])
    assert [branch for branch, _, _ in planned] == [
        "auto/tests-integration-config",
        "auto/tests-unit-config",
    ]


def _ended(key: str, **change: Any) -> dict[str, Any]:
    return {**OUTCOME, "key": key, **change}


def test_a_fix_with_an_outcome_isnt_planned_again(tmp_path: Path) -> None:
    """Planning a run again takes up what is missing; what a review rejected is the operator's."""
    fixes = [_fix("a", [SHAPES]), _fix("b", [SHAPES]), _fix("c", [LOG]), _fix("d", [CONFIG])]
    rejected = {**REVIEW, "accept": False}
    _write(tmp_path / "outcomes.jsonl", [_ended("dod-gap:a"), _ended("dod-gap:c", review=rejected)])
    # What is left of the accepted fix's file follows it on its branch
    assert _plan(tmp_path, fixes) == [
        ("auto/tests-shapes", [SHAPES], ["dod-gap:b"]),
        ("auto/tests-unit-config", [CONFIG], ["dod-gap:d"]),
    ]


def test_a_fix_whose_agent_didnt_answer_is_planned_again(tmp_path: Path) -> None:
    _write(tmp_path / "outcomes.jsonl", [_ended("dod-gap:a", fixed=None, review=None)])
    assert _plan(tmp_path, [_fix("a", [SHAPES])]) == [
        ("auto/tests-unit-shapes", [SHAPES], ["dod-gap:a"]),
    ]


def test_a_fix_whose_test_belongs_elsewhere_is_planned_again_in_that_file(tmp_path: Path) -> None:
    """Its agent named the file another branch held; the next plan gives it that file."""
    elsewhere = {**NOTHING_COMMITTED, "status": "elsewhere", "notes": f"The test belongs in {LOG}."}
    _write(tmp_path / "outcomes.jsonl", [_ended("dod-gap:a", fixed=elsewhere, review=None)])
    assert _plan(tmp_path, [_fix("a", [SHAPES])]) == [
        ("auto/tests-unit-log", [LOG], ["dod-gap:a"]),
    ]


def test_a_fix_refuted_beside_a_rejected_one_is_planned_again(tmp_path: Path) -> None:
    """An earlier test on the branch may have closed its gap, and that test is dropped."""
    branch = "auto/tests-unit-shapes"
    refuted = {**NOTHING_COMMITTED, "status": "refuted", "notes": "dod-gap:a's test closes it"}
    rejected = {**REVIEW, "accept": False}
    _write(
        tmp_path / "outcomes.jsonl",
        [
            _ended("dod-gap:a", branch=branch, review=rejected),
            _ended("dod-gap:b", branch=branch, fixed=refuted, review=None),
            _ended("dod-gap:c", branch="auto/tests-unit-log", fixed=refuted, review=None),
        ],
    )
    fixes = [_fix("a", [SHAPES]), _fix("b", [SHAPES]), _fix("c", [LOG])]
    assert _plan(tmp_path, fixes) == [("auto/tests-unit-shapes", [SHAPES], ["dod-gap:b"])]


def _accepted(key: str, branch: str, *files: str) -> dict[str, Any]:
    """The outcome of a fix a review accepted, its tests in these files on this branch."""
    fixed = {**FIXED, "tests": [f"{path}::test_it" for path in files]}
    return _ended(key, branch=branch, fixed=fixed)


def test_planning_again_keeps_a_files_branch(tmp_path: Path) -> None:
    """A branch named after another of its files holds this one's accepted commits."""
    branch = "auto/tests-unit-config"
    _write(tmp_path / "outcomes.jsonl", [_accepted("dod-gap:b", branch, CONFIG, SHAPES)])
    fixes = [_fix("a", [SHAPES]), _fix("b", [CONFIG, SHAPES])]
    assert _plan(tmp_path, fixes) == [(branch, [SHAPES], ["dod-gap:a"])]


def test_a_group_that_splits_stays_on_its_one_branch(tmp_path: Path) -> None:
    """The fix that tied two files together is done; the branch still holds both files'
    commits, so what is left of them stays one group and no two groups claim the branch."""
    branch = "auto/tests-unit-config"
    _write(tmp_path / "outcomes.jsonl", [_accepted("dod-gap:b", branch, CONFIG, SHAPES)])
    fixes = [_fix("a", [SHAPES]), _fix("b", [CONFIG, SHAPES]), _fix("c", [CONFIG])]
    assert _plan(tmp_path, fixes) == [(branch, [CONFIG, SHAPES], ["dod-gap:a", "dod-gap:c"])]


def test_a_branch_holding_nothing_a_review_accepted_isnt_kept(tmp_path: Path) -> None:
    """Its commits are dropped, so nothing there is built on."""
    rejected = _accepted("dod-gap:b", "auto/tests-unit-config", CONFIG, SHAPES)
    _write(tmp_path / "outcomes.jsonl", [{**rejected, "review": {**REVIEW, "accept": False}}])
    fixes = [_fix("a", [SHAPES]), _fix("b", [CONFIG, SHAPES])]
    assert _plan(tmp_path, fixes) == [("auto/tests-unit-shapes", [SHAPES], ["dod-gap:a"])]


def test_a_group_with_files_of_two_branches_names_the_other(tmp_path: Path) -> None:
    """A fix moved to another branch's file ties the two; the operator merges the other first."""
    outcomes = [
        _accepted("dod-gap:a", "auto/tests-unit-config", CONFIG),
        _accepted("dod-gap:b", "auto/tests-unit-shapes", SHAPES),
    ]
    _write(tmp_path / "outcomes.jsonl", outcomes)
    fixes = [_fix("a", [CONFIG]), _fix("b", [SHAPES]), _fix("c", [CONFIG, SHAPES])]
    assert _plan(tmp_path, fixes) == [
        ("auto/tests-unit-config", [CONFIG, SHAPES], ["dod-gap:c"]),
    ]
    [group] = json.loads((tmp_path / "groups.json").read_text())
    assert group["also"] == ["auto/tests-unit-shapes"]


def test_a_fix_planned_once_more_keeps_its_second_outcome(tmp_path: Path) -> None:
    """Else one refuted beside a rejected fix would be planned at every plan after."""
    branch = "auto/tests-unit-shapes"
    refuted = {**NOTHING_COMMITTED, "status": "refuted", "notes": "a test closes it"}
    elsewhere = {**NOTHING_COMMITTED, "status": "elsewhere", "notes": f"It belongs in {LOG}."}
    _write(
        tmp_path / "outcomes.jsonl",
        [
            _ended("dod-gap:a", branch=branch, review={**REVIEW, "accept": False}),
            _ended("dod-gap:b", branch=branch, fixed=refuted, review=None, replaced="refuted"),
            _ended("dod-gap:c", fixed=elsewhere, review=None, replaced="elsewhere"),
        ],
    )
    assert _plan(tmp_path, [_fix("a", [SHAPES]), _fix("b", [SHAPES]), _fix("c", [CONFIG])]) == []


def test_the_plan_names_a_branch_that_holds_commits_no_review_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A fix there would build on a test that is dropped, or find its gap closed by it."""
    branch = "auto/tests-unit-shapes"
    rejected = _ended("dod-gap:a", branch=branch, review={**REVIEW, "accept": False})
    _write(tmp_path / "outcomes.jsonl", [rejected])
    _plan(tmp_path, [_fix("a", [SHAPES]), _fix("b", [SHAPES]), _fix("c", [CONFIG])])
    assert capsys.readouterr().err.splitlines() == [
        f"{branch} holds commits no review accepted (outcomes.json): drop them before the fix stage"
    ]


def _with_ratchet(run: Path, **outcome: Any) -> list[dict[str, Any]]:
    key = f"ratchet:{AT_THE_LIMIT}"
    ratchet = {
        "key": key,
        "slug": f"ratchet-{AT_THE_LIMIT}",
        "findings": ["dod-gap:a", "dod-gap:c"],
    }
    fixes = [_fix("a", [SHAPES], ratchet=AT_THE_LIMIT), _fix("c", [CONFIG], ratchet=AT_THE_LIMIT)]
    _write(run / "outcomes.jsonl", [_ended(key, **outcome)])
    _plan(run, fixes, ratchet)
    groups: list[dict[str, Any]] = json.loads((run / "groups.json").read_text())
    return groups


def test_a_ratchet_no_review_accepted_is_left_out_and_its_findings_planned_alone(
    tmp_path: Path,
) -> None:
    """Each finding then gets its own test, on the branch of its file, not on the ratchet's,
    where the rejected test stands."""
    branch = f"auto/tests-ratchet-{AT_THE_LIMIT}"
    groups = _with_ratchet(tmp_path, branch=branch, review={**REVIEW, "accept": False})
    assert [(g["branch"], g["ratchets"]) for g in groups] == [
        ("auto/tests-unit-config", []),
        ("auto/tests-unit-shapes", []),
    ]
    assert [f["ratchet"] for g in groups for f in g["fixes"]] == [None, None]


def test_an_accepted_ratchet_isnt_run_again_and_its_findings_stay_on_its_branch(
    tmp_path: Path,
) -> None:
    """Its test is on that branch; the findings left add only what it leaves open."""
    groups = _with_ratchet(tmp_path, branch=f"auto/tests-ratchet-{AT_THE_LIMIT}")
    assert [(g["branch"], g["ratchets"]) for g in groups] == [
        (f"auto/tests-ratchet-{AT_THE_LIMIT}", []),
    ]
    assert [f["key"] for f in groups[0]["fixes"]] == ["dod-gap:a", "dod-gap:c"]
    # Their agents are told the generic test is there, though this stage didn't run it
    assert [f["ratchet_done"] for f in groups[0]["fixes"]] == [True, True]


def test_the_gate_refuses_a_test_file_planned_for_another_branch() -> None:
    groups = [
        {"branch": "auto/tests-unit-shapes", "files": [SHAPES]},
        {"branch": "auto/tests-unit-log", "files": [LOG]},
    ]
    elsewhere = gate.planned_elsewhere(groups, "auto/tests-unit-shapes")
    assert elsewhere == {LOG: "auto/tests-unit-log"}
    paths = [SHAPES, LOG, "tests/unit/test_new.py"]
    found = gate.problems("auto/tests-unit-shapes", ["test: t"], paths, elsewhere=elsewhere)
    assert found == [f"{LOG} is planned for auto/tests-unit-log"]
    assert gate.problems("auto/tests-unit-shapes", ["test: t"], [SHAPES], elsewhere=elsewhere) == []


@pytest.mark.parametrize(
    ("output", "unproven"),
    [
        ("1206 passed, 191 skipped in 18.11s", 191),
        ("........\n1398 passed in 61.20s (0:01:01)", 0),
        ("F..\n1 failed, 2 passed, 3 skipped, 1 warning in 0.40s", 3),
        ("1390 passed, 2 deselected, 1 xfailed, 1 xpassed in 60.01s", 4),
    ],
)
def test_the_gate_counts_the_tests_that_proved_nothing(output: str, unproven: int) -> None:
    """Every gate green means every test ran and had to pass: one skipped, expected to
    fail or left out proves nothing."""
    assert gate.unproven(output) == unproven


def test_the_gate_names_a_test_that_no_longer_passes_in_every_case() -> None:
    """ADR-008: a test goes only when it kills no mutant another doesn't; the operator decides."""
    a, b, c = (f"tests/unit/test_a.py::test_{name}" for name in "abc")
    before = {a: 1, b: 3, c: 1}
    assert (
        gate.no_longer_passing(before, {a: 1, b: 4, c: 1, "tests/unit/test_new.py::test": 2}) == []
    )
    assert gate.no_longer_passing(before, {a: 1, b: 2, "tests/unit/test_b.py::test_c": 1}) == [
        f"{b} passes in 2 of 3 cases",
        f"{c} passes in 0 of 1 cases",
    ]


PROJECT = {
    "test_a.py": (
        "import pytest\n\n"
        "def test_plain():\n    assert True\n\n"
        "@pytest.mark.parametrize('n', [1, 2, 3], ids=['one', 'a b', 'c[d]'])\n"
        "def test_cases(n):\n    assert n\n\n"
        "def test_kept():\n    assert True\n\n"
        "def test_moved():\n    assert True\n"
    ),
}
WEAKENED = {
    "test_a.py": (
        "import pytest\n\n"
        "@pytest.mark.xfail\ndef test_plain():\n    assert False\n\n"
        "@pytest.mark.parametrize('n', [1, 2], ids=['one', 'a b'])\n"
        "def test_cases(n):\n    assert n\n\n"
        "def test_kept():\n    assert True\n\n"
        "def test_added():\n    assert True\n"
    ),
    # A file pytest doesn't look into
    "helpers.py": "def test_moved():\n    assert True\n",
}


def _pytest(folder: Path, files: dict[str, str], *args: str) -> str:
    for name, text in files.items():
        (folder / name).write_text(text)
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", os.devnull, *args],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


def test_the_gate_reads_from_pytest_which_tests_main_had_and_which_passed(tmp_path: Path) -> None:
    """Whatever keeps a test from proving something: the gate compares what ran and passed."""
    before = gate.tests_collected(_pytest(tmp_path, PROJECT, "--collect-only"))
    assert before == {
        "test_a.py::test_plain": 1,
        "test_a.py::test_cases": 3,
        "test_a.py::test_kept": 1,
        "test_a.py::test_moved": 1,
    }
    assert (
        gate.no_longer_passing(before, gate.tests_passed(_pytest(tmp_path, PROJECT, "-rp"))) == []
    )
    output = _pytest(tmp_path, WEAKENED, "-rp")
    assert gate.no_longer_passing(before, gate.tests_passed(output)) == [
        "test_a.py::test_cases passes in 2 of 3 cases",
        "test_a.py::test_moved passes in 0 of 1 cases",
        "test_a.py::test_plain passes in 0 of 1 cases",
    ]
    assert gate.unproven(output) == 1


def test_a_branch_that_passed_at_its_commit_is_pushed_without_a_second_run() -> None:
    green = {"ruff": True, "tests": True}
    records: list[dict[str, Any]] = [
        {"branch": "auto/x", "commit": "c1", "passed": False, "checks": {"tests": False}},
        {"branch": "auto/x", "commit": "c2", "passed": True, "checks": green},
        {"branch": "auto/y", "commit": "c3", "passed": True, "checks": green},
    ]
    assert gate.passed_earlier(records, "auto/x", "c2") == green
    # Another commit of the branch, or another branch at that commit: run the checks
    assert gate.passed_earlier(records, "auto/x", "c1") is None
    assert gate.passed_earlier(records, "auto/y", "c2") is None


def _git(cwd: Path, *args: str) -> str:
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        ["git", *identity, *args],  # noqa: S607 - git from PATH, as the harness
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _worktree(repo: Path, name: str, *, commit: bool, branch: str | None = None) -> Path:
    """A worktree as the fix workflow leaves one: on a branch of its own, the agent detached,
    its commit (if any) on the auto/ branch it moved (if any)."""
    tree = repo / ".claude" / "worktrees" / f"wf_{name}"
    _git(repo, "worktree", "add", "-q", "-b", f"worktree-wf_{name}", str(tree), "main")
    _git(tree, "switch", "-q", "--detach")
    if commit:
        (tree / f"{name}.txt").write_text(name)
        _git(tree, "add", ".")
        _git(tree, "commit", "-q", "-m", f"test: {name}")
    if branch:
        _git(tree, "branch", "-f", branch, "HEAD")
    return tree


def _cloned(tmp_path: Path) -> tuple[Path, Path]:
    """A repository on GitHub's side and a clone of it, both at one commit on main."""
    upstream, clone = tmp_path / "upstream", tmp_path / "clone"
    upstream.mkdir()
    _git(upstream, "init", "-q", "-b", "main")
    _git(upstream, "commit", "-q", "--allow-empty", "-m", "chore: start")
    _git(tmp_path, "clone", "-q", str(upstream), str(clone))
    return upstream, clone


def test_the_gate_and_the_cleanup_compare_with_main_as_the_remote_has_it() -> None:
    """A local main behind the remote's would count its merged commits as a branch's own."""
    assert gate.BASE == cleanup.BASE == "origin/main"


def test_a_remote_base_is_fetched_before_it_is_compared(tmp_path: Path) -> None:
    upstream, clone = _cloned(tmp_path)
    _git(upstream, "commit", "-q", "--allow-empty", "-m", "fix: merged since the last fetch")
    merged = _git(upstream, "rev-parse", "HEAD")
    gate.fetch(clone, "origin/main")
    assert _git(clone, "rev-parse", "origin/main") == merged


def test_a_local_base_is_left_as_it_is(tmp_path: Path) -> None:
    upstream, clone = _cloned(tmp_path)
    before = _git(clone, "rev-parse", "origin/main")
    _git(upstream, "commit", "-q", "--allow-empty", "-m", "fix: merged since the last fetch")
    gate.fetch(clone, "main")
    assert _git(clone, "rev-parse", "origin/main") == before


def test_cleanup_removes_only_worktrees_whose_commits_are_on_an_auto_branch(
    tmp_path: Path,
) -> None:
    """Nothing is lost: a commit on no auto/ branch, a lock or a change keeps its worktree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "chore: base")
    _worktree(repo, "done", commit=True, branch="auto/tests-a")
    _worktree(repo, "lost", commit=True)
    locked = _worktree(repo, "locked", commit=True, branch="auto/tests-b")
    _git(repo, "worktree", "lock", str(locked))
    dirty = _worktree(repo, "dirty", commit=True, branch="auto/tests-c")
    (dirty / "left.txt").write_text("not committed")
    _worktree(repo, "idle", commit=False)

    found = cleanup.survey(repo, "main")
    assert [tree.name for tree in found.worktrees] == ["wf_done"]
    assert found.branches == ["worktree-wf_done"]
    assert {tree.name: why for tree, why in found.kept} == {
        "wf_dirty": "uncommitted changes",
        "wf_idle": "no commits: an agent may be starting in it",
        "wf_locked": "locked: an agent is running in it",
        "wf_lost": "its commits are on no auto/ branch",
    }
    # Once the workflow has ended, a worktree without commits is done with too
    after = cleanup.survey(repo, "main", finished=True)
    assert [tree.name for tree in after.worktrees] == ["wf_done", "wf_idle"]

    assert cleanup.main(repo, "main", remove=False, finished=False) == 0
    assert (repo / ".claude" / "worktrees" / "wf_done").is_dir()
    assert cleanup.main(repo, "main", remove=True, finished=False) == 0
    left = sorted(tree.name for tree in (repo / ".claude" / "worktrees").iterdir())
    assert left == ["wf_dirty", "wf_idle", "wf_locked", "wf_lost"]
    branches = _git(repo, "branch", "--format=%(refname:short)").splitlines()
    assert "worktree-wf_done" not in branches
    assert {"worktree-wf_lost", "auto/tests-a"} <= set(branches)


def _with_worktrees(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "chore: base")
    return repo


def test_cleanup_prunes_a_worktree_whose_folder_is_gone(tmp_path: Path) -> None:
    """Deleted by hand or by a crashed agent: git still lists it until it is pruned."""
    repo = _with_worktrees(tmp_path)
    gone = _worktree(repo, "gone", commit=True, branch="auto/tests-a")
    _worktree(repo, "done", commit=True, branch="auto/tests-b")
    shutil.rmtree(gone)
    assert [tree.name for tree in cleanup.survey(repo, "main").missing] == ["wf_gone"]
    assert cleanup.main(repo, "main", remove=True, finished=False) == 0
    assert "wf_gone" not in _git(repo, "worktree", "list")
    assert not (repo / ".claude" / "worktrees" / "wf_done").exists()


def test_cleanup_keeps_a_missing_worktree_whose_commits_are_on_no_auto_branch(
    tmp_path: Path,
) -> None:
    """A crashed agent's commit is reachable only through git's record of its worktree."""
    repo = _with_worktrees(tmp_path)
    lost = _worktree(repo, "lost", commit=True)
    commit = _git(lost, "rev-parse", "HEAD")
    shutil.rmtree(lost)
    found = cleanup.survey(repo, "main")
    assert (found.missing, found.branches) == ([], [])
    assert [(tree.name, why) for tree, why in found.kept] == [
        ("wf_lost", "its commits are on no auto/ branch")
    ]
    assert cleanup.main(repo, "main", remove=True, finished=False) == 0
    assert f"HEAD {commit}" in _git(repo, "worktree", "list", "--porcelain")


def test_cleanup_leaves_the_repositorys_other_worktrees_alone(tmp_path: Path) -> None:
    """One of the operator's whose folder is away, on a disk not mounted, stays listed."""
    repo = _with_worktrees(tmp_path)
    other = tmp_path / "elsewhere"
    _git(repo, "worktree", "add", "-q", "-b", "feat/mine", str(other), "main")
    shutil.rmtree(other)
    shutil.rmtree(_worktree(repo, "gone", commit=False))
    assert cleanup.main(repo, "main", remove=True, finished=False) == 0
    listed = _git(repo, "worktree", "list", "--porcelain")
    assert "wf_gone" not in listed
    assert str(other) in listed


def test_cleanup_goes_on_past_a_worktree_git_wont_remove(tmp_path: Path) -> None:
    """One changed since the survey keeps its branch; the others go."""
    repo = _with_worktrees(tmp_path)
    changed = _worktree(repo, "changed", commit=True, branch="auto/tests-a")
    _worktree(repo, "done", commit=True, branch="auto/tests-b")
    found = cleanup.survey(repo, "main")
    (changed / "late.txt").write_text("written after the survey")
    removed = cleanup.clear(repo, found)
    assert [tree.name for tree in removed] == ["wf_done"]
    assert changed.is_dir()
    branches = _git(repo, "branch", "--format=%(refname:short)").splitlines()
    assert "worktree-wf_changed" in branches
    assert "worktree-wf_done" not in branches


def _result(run: Path, result: dict[str, Any], **more: Any) -> Path:
    path = run / "workflow.output"
    path.write_text(json.dumps({"agentCount": 7, "totalTokens": 1000, "result": result, **more}))
    return path


def test_a_surveys_result_becomes_the_runs_findings(tmp_path: Path) -> None:
    """The session no longer writes a workflow's result to the records by hand."""
    result = {"records": [FINDING], "unverified": [DOD_GAP], "surveysFailed": 0}
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [FINDING]
    assert _lines(tmp_path / "unverified.jsonl") == [DOD_GAP]
    assert _lines(tmp_path / "workflows.jsonl") == [
        {"wrote": "findings", "records": 1, "agents": 7, "tokens": 1000}
    ]


def test_a_survey_recorded_again_replaces_only_what_its_surveys_found(tmp_path: Path) -> None:
    """The sweep's findings and those of a survey that didn't answer this time stay."""
    old = {**FINDING, "origin": "spec:req-001-core.md"}
    swept = {**FINDING, "mutants": [MUTANT_ELSEWHERE], "origin": f"sweep:mutant-gap:{MUTANT}"}
    unanswered = {**DOD_GAP, "origin": "mutants:2"}
    _write(tmp_path / "findings.jsonl", [old, swept, unanswered])
    new = {**old, "claim": "found again"}
    result = {
        "records": [new],
        "unverified": [],
        "surveysFailed": 1,
        "surveyed": ["spec:req-001-core.md", "mutants:1"],
    }
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [swept, unanswered, new]


def test_a_survey_result_without_its_surveys_keeps_the_sweeps_findings(tmp_path: Path) -> None:
    swept = {**FINDING, "origin": f"sweep:mutant-gap:{MUTANT}"}
    _write(tmp_path / "findings.jsonl", [{**DOD_GAP, "origin": "spec:a"}, swept])
    result: dict[str, Any] = {"records": [], "unverified": [], "surveysFailed": 0}
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [swept]


def test_a_finding_the_sweep_holds_isnt_recorded_again_by_a_survey(tmp_path: Path) -> None:
    """What stays and what comes are compared too: one record per key, the first."""
    swept = {**FINDING, "origin": f"sweep:mutant-gap:{MUTANT}"}
    waiting = {**DOD_GAP, "origin": "mutants:2", "verdict": None}
    _write(tmp_path / "findings.jsonl", [swept])
    _write(tmp_path / "unverified.jsonl", [waiting])
    found_again = {**FINDING, "claim": "found again", "origin": "mutants:1"}
    judged_now = {**DOD_GAP, "origin": "spec:a"}
    result = {"records": [found_again, judged_now], "unverified": [], "surveyed": ["mutants:1"]}
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [
        {**swept, "also": ["mutants:1"]},
        {**judged_now, "also": ["mutants:2"]},
    ]
    assert _lines(tmp_path / "unverified.jsonl") == []
    assert triage.main(tmp_path) == 0
    # Recorded once more, as a resumed workflow returns it: nothing changes
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl")[0] == {**swept, "also": ["mutants:1"]}


def test_a_finding_two_surveys_made_is_recorded_once(tmp_path: Path) -> None:
    """Triage refuses two records with one key, and the whole run with them."""
    weak = {**DOD_GAP, "kind": "weak-test", "location": "tests/unit/test_a.py::test_b"}
    first, second = {**weak, "origin": "spec:a"}, {**weak, "origin": "spec:b"}
    later = {**weak, "origin": "spec:c", "verdict": None}
    result = {"records": [first, second], "unverified": [later], "surveysFailed": 0}
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [{**first, "also": ["spec:b", "spec:c"]}]
    assert _lines(tmp_path / "unverified.jsonl") == []


def test_a_fix_stages_result_becomes_the_runs_outcomes(tmp_path: Path) -> None:
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": [OUTCOME]})) == 0
    assert _lines(tmp_path / "outcomes.jsonl") == [OUTCOME]


def test_a_second_fix_stage_adds_its_outcomes_and_replaces_an_agents_missing_answer(
    tmp_path: Path,
) -> None:
    """The plan hands a fix whose agent didn't answer to the next fix stage."""
    unanswered = {**OUTCOME, "key": OTHER_KEY, "fixed": None, "review": None}
    _write(tmp_path / "outcomes.jsonl", [OUTCOME, unanswered])
    answered = {**OUTCOME, "key": OTHER_KEY}
    third = {**OUTCOME, "key": "dod-gap:new"}
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": [answered, third]})) == 0
    assert _lines(tmp_path / "outcomes.jsonl") == [OUTCOME, answered, third]


def test_a_fix_the_plan_handed_out_once_more_gets_its_second_outcome(tmp_path: Path) -> None:
    """One whose test belonged elsewhere, and one refuted beside a rejected fix: the record
    says what it replaced, and the plan doesn't hand it out a third time."""
    branch = "auto/tests-unit-shapes"
    elsewhere = {**NOTHING_COMMITTED, "status": "elsewhere", "notes": f"It belongs in {LOG}."}
    refuted = {**NOTHING_COMMITTED, "status": "refuted", "notes": "a test closes it"}
    rejected = _ended("dod-gap:a", branch=branch, review={**REVIEW, "accept": False})
    moved = _ended("dod-gap:b", fixed=elsewhere, review=None)
    closed = _ended("dod-gap:c", branch=branch, fixed=refuted, review=None)
    _write(tmp_path / "outcomes.jsonl", [rejected, moved, closed])
    second = [_ended("dod-gap:b", branch="auto/tests-unit-log"), _ended("dod-gap:c", branch=branch)]
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": second})) == 0
    assert _lines(tmp_path / "outcomes.jsonl") == [
        rejected,
        {**second[0], "replaced": "elsewhere"},
        {**second[1], "replaced": "refuted"},
    ]
    # The same again, from a resumed workflow, changes nothing; a third outcome is refused
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": second})) == 0
    third = [{**second[0], "review": {**REVIEW, "accept": False}}]
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": third})) == 1
    assert _lines(tmp_path / "outcomes.jsonl")[1] == {**second[0], "replaced": "elsewhere"}


def test_a_second_fix_stage_runs_from_plan_to_outcomes(tmp_path: Path) -> None:
    """The scripts in the order of a run, twice: what the first stage left is planned,
    recorded and counted, and a third plan finds nothing to do."""
    elsewhere = {**NOTHING_COMMITTED, "status": "elsewhere", "notes": f"It belongs in {LOG}."}
    fixes = [_fix("a", [SHAPES]), _fix("b", [SHAPES]), _fix("c", [CONFIG]), _fix("d", [CONFIG])]
    first = _plan(tmp_path, fixes)
    assert [branch for branch, _, _ in first] == [
        "auto/tests-unit-config",
        "auto/tests-unit-shapes",
    ]
    stage = [
        _accepted("dod-gap:a", "auto/tests-unit-shapes", SHAPES),
        _ended("dod-gap:b", branch="auto/tests-unit-shapes", fixed=elsewhere, review=None),
        _accepted("dod-gap:c", "auto/tests-unit-config", CONFIG),
        _ended("dod-gap:d", branch="auto/tests-unit-config", fixed=None, review=None),
    ]
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": stage})) == 0
    assert outcomes.main(tmp_path) == 0
    assert _plan(tmp_path, fixes) == [
        ("auto/tests-unit-config", [CONFIG], ["dod-gap:d"]),
        ("auto/tests-unit-log", [LOG], ["dod-gap:b"]),
    ]
    stage = [
        _accepted("dod-gap:b", "auto/tests-unit-log", LOG),
        _accepted("dod-gap:d", "auto/tests-unit-config", CONFIG),
    ]
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": stage})) == 0
    assert outcomes.main(tmp_path) == 0
    summary = json.loads((tmp_path / "outcomes.json").read_text())
    assert (summary["states"], summary["missing"]) == ({"accepted": 4}, [])
    assert _plan(tmp_path, fixes) == []


def test_a_second_outcome_for_a_fix_that_has_one_is_refused(tmp_path: Path) -> None:
    before = _write(tmp_path / "outcomes.jsonl", [OUTCOME]).read_text()
    again = {**OUTCOME, "review": {**REVIEW, "accept": False}}
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": [again]})) == 1
    assert (tmp_path / "outcomes.jsonl").read_text() == before
    assert not (tmp_path / "workflows.jsonl").exists()


def test_a_resumed_fix_stage_may_return_the_same_outcome_again(tmp_path: Path) -> None:
    """A workflow resumed after a stop replays its finished agents' answers."""
    _write(tmp_path / "outcomes.jsonl", [OUTCOME])
    assert record.main(tmp_path, _result(tmp_path, {"outcomes": [OUTCOME]})) == 0
    assert _lines(tmp_path / "outcomes.jsonl") == [OUTCOME]


@pytest.mark.parametrize("result", [None, [], {"groups": []}, {"records": {}}, {"outcomes": [1]}])
def test_a_result_of_no_known_shape_is_refused(tmp_path: Path, result: Any) -> None:
    """A workflow that failed leaves no result; nothing is written from it."""
    assert record.main(tmp_path, _result(tmp_path, result)) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["workflow.output"]


# The sweep: a confirmed finding's class wherever the survivors show it


def _survivor(mutant: str, diff: str, filter: str | None = None) -> dict[str, Any]:
    return {"id": mutant, "module": mutant.split(".x")[0], "filter": filter, "diff": diff}


REFUSE = '        raise drafts.refuse_duplicates(matches, PAYMENT_MATCH, "payment entry")'
FOUND = "enterich.tools.procure_to_pay.x_create_draft_purchase_invoice__mutmut_85"
LIKE: dict[str, Any] = {
    **FINDING,
    "location": "src/enterich/tools/procure_to_pay.py:create_draft_purchase_invoice",
    "mutants": [FOUND],
    "verdict": {**FINDING["verdict"], "pattern": "text-by-part", "test_files": []},
}
OWN = {"refuse_duplicates", "duplicate_warning", "create_draft_payment_entry"}


@pytest.mark.parametrize(
    ("diff", "changed"),
    [
        (f"-{REFUSE}\n+{REFUSE.replace('PAYMENT_MATCH', 'None')}", "refuse_duplicates"),
        (f"-{REFUSE}\n+{REFUSE.replace('PAYMENT_MATCH, ', '')}", "refuse_duplicates"),
        (
            '-def duplicate_warning(names, match, kind="draft") -> str:\n'
            '+def duplicate_warning(names, match, kind="XXdraftXX") -> str:',
            "duplicate_warning",
        ),
        ("-    if len(missing) > 3:\n+    if len(missing) >= 3:", None),
        (f"-{REFUSE}\n-    x = 1\n+{REFUSE.replace('PAYMENT_MATCH', 'None')}", None),
    ],
)
def test_the_sweep_names_the_call_or_definition_a_mutant_changed(
    diff: str, changed: str | None
) -> None:
    """Only a mutant of one line: a change spread over lines has no single call."""
    assert sweep.callee(diff) == changed


MODULES = {"drafts", "config"}


@pytest.mark.parametrize(
    ("diff", "changed"),
    [
        # Inside a call of Python's, the project's own call
        ('-    return str(optional(name, "a"))\n+    return str(optional(name, None))', "optional"),
        ('-    x = cast("T", drafts.named(n))\n+    x = cast("T", drafts.named(None))', "named"),
        ("-    self._verify(token, key)\n+    self._verify(token, None)", "_verify"),
        # A library's call that shares a name with one of the project's
        ("-    data = tomllib.load(file)\n+    data = tomllib.load(None)", None),
        ("-    return response.text(limit)\n+    return response.text(None)", None),
    ],
)
def test_the_sweep_follows_the_projects_own_call_however_deep(
    diff: str, changed: str | None
) -> None:
    own = {"optional", "named", "_verify", "load", "text"}
    assert sweep.callee(diff, own, MODULES) == changed


def test_the_sweep_knows_the_projects_modules(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "__init__.py").write_text("")
    (tmp_path / "tools" / "drafts.py").write_text("")
    (tmp_path / "config.py").write_text("")
    assert sweep.module_names(tmp_path) == {"tools", "drafts", "config"}


def test_the_sweep_knows_the_projects_own_functions_and_classes(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def one():\n    pass\nclass Two:\n    async def three(self): ...\n"
    )
    assert sweep.own_names(tmp_path) == {"one", "Two", "three"}


def test_the_sweep_gives_each_survivor_its_function_as_location() -> None:
    assert sweep.location(
        "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_30"
    ) == ("src/enterich/tools/bank_and_cash.py:create_draft_payment_entry")
    assert sweep.location("enterich.auth.xǁVerifierǁ_verify__mutmut_4") == (
        "src/enterich/auth.py:Verifier._verify"
    )


def test_the_sweep_takes_the_survivors_no_finding_named_that_change_the_same_call() -> None:
    changed = f"-{REFUSE}\n+{REFUSE.replace('PAYMENT_MATCH', 'None')}"
    survivors = [
        _survivor(FOUND, changed),
        _survivor("enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_30", changed),
        _survivor("enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_31", changed),
        # A script judged it already
        _survivor(
            "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_35",
            changed,
            "message",
        ),
        # Named in a finding not verified
        _survivor(
            "enterich.tools.record_to_report.x_create_draft_journal_entry__mutmut_18", changed
        ),
        # Another call
        _survivor(
            "enterich.tools.order_to_cash.x_create_draft_sales_invoice__mutmut_7",
            '-    x = rows.get("a")\n+    x = rows.get(None)',
        ),
    ]
    unverified = [
        {
            **LIKE,
            "mutants": ["enterich.tools.record_to_report.x_create_draft_journal_entry__mutmut_18"],
        }
    ]
    [swept] = sweep.swept(survivors, [LIKE], unverified, OWN)
    assert swept["location"] == "src/enterich/tools/bank_and_cash.py:create_draft_payment_entry"
    assert swept["mutants"] == [
        "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_30",
        "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_31",
    ]
    assert (swept["kind"], swept["origin"], swept["like"]) == (
        "mutant-gap",
        f"sweep:mutant-gap:{FOUND}",
        f"mutant-gap:{FOUND}",
    )
    # A candidate of an earlier sweep that no verifier judged is offered again
    waiting = [{**unverified[0], "origin": f"sweep:mutant-gap:{FOUND}"}]
    assert len(sweep.swept(survivors, [LIKE], waiting, OWN)) == 2
    # A record as triage takes it, once a verifier has judged it
    verdict: dict[str, Any] = {
        "confirmed": True,
        "class": "fix",
        "pattern": None,
        "test_files": [],
        "reason": "x",
    }
    assert triage.check({**swept, "verdict": verdict}) == []


@pytest.mark.parametrize(
    "like",
    [
        {**LIKE, "verdict": {**LIKE["verdict"], "confirmed": False, "class": "drop"}},
        {
            **LIKE,
            "kind": "dod-gap",
            "location": "req-001-core.md#REQ-001-PRS-F005 item 1",
            "mutants": [],
        },
    ],
)
def test_the_sweep_follows_only_a_confirmed_mutant_gap(like: dict[str, Any]) -> None:
    changed = f"-{REFUSE}\n+{REFUSE.replace('PAYMENT_MATCH', 'None')}"
    other = "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_30"
    survivors = [_survivor(FOUND, changed), _survivor(other, changed)]
    assert sweep.swept(survivors, [like], [], OWN) == []


def test_the_sweep_leaves_a_call_of_python_or_a_library_alone() -> None:
    """Every dict's get is no class of finding."""
    changed = '-    x = rows.get("a")\n+    x = rows.get(None)'
    other = "enterich.tools.order_to_cash.x_create_draft_sales_invoice__mutmut_7"
    survivors = [_survivor(FOUND, changed), _survivor(other, changed)]
    assert sweep.swept(survivors, [LIKE], [], OWN | {"x_create_draft_sales_invoice"}) == []


def test_the_sweep_finds_what_the_fourth_runs_survey_missed() -> None:
    """The survey found the duplicate texts checked by a part in two modules; the same
    mutants survived in three more, and at the helper's default."""
    run = inventory.ROOT / "harness" / "runs" / "2026-11-14-tests-2"
    swept = sweep.swept(
        _lines(run / "survivors.jsonl"),
        _lines(run / "findings.jsonl"),
        _lines(run / "unverified.jsonl"),
        sweep.own_names(),
        sweep.module_names(),
    )
    assert {s["location"]: len(s["mutants"]) for s in swept} == {
        "src/enterich/tools/bank_and_cash.py:create_draft_payment_entry": 8,
        "src/enterich/tools/bank_and_cash.py:update_draft_payment_entry": 4,
        "src/enterich/tools/drafts.py:duplicate_warning": 2,
        "src/enterich/tools/order_to_cash.py:create_draft_sales_invoice": 1,
        "src/enterich/tools/record_to_report.py:create_draft_journal_entry": 2,
    }


def test_the_sweep_writes_its_candidates_for_the_verifiers(tmp_path: Path) -> None:
    changed = f"-{REFUSE}\n+{REFUSE.replace('PAYMENT_MATCH', 'None')}"
    other = "enterich.tools.bank_and_cash.x_create_draft_payment_entry__mutmut_30"
    _write(tmp_path / "survivors.jsonl", [_survivor(FOUND, changed), _survivor(other, changed)])
    _write(tmp_path / "findings.jsonl", [LIKE])
    src = tmp_path / "src"
    src.mkdir()
    (src / "drafts.py").write_text("def refuse_duplicates(): ...\n")
    assert sweep.main(tmp_path, src) == 0
    [candidate] = _lines(tmp_path / "sweep.jsonl")
    assert candidate["mutants"] == [other]


def test_a_sweeps_verdicts_are_added_to_the_runs_findings(tmp_path: Path) -> None:
    """Unlike a survey's, which are the run's findings whole."""
    _write(tmp_path / "findings.jsonl", [FINDING])
    _write(tmp_path / "unverified.jsonl", [DOD_GAP])
    swept = {**LIKE, "origin": f"sweep:mutant-gap:{MUTANT}"}
    later = {**swept, "mutants": [MUTANT_ELSEWHERE], "verdict": None}
    result = {"records": [swept], "unverified": [later], "surveysFailed": 0, "sweep": True}
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [FINDING, swept]
    assert _lines(tmp_path / "unverified.jsonl") == [DOD_GAP, later]
    assert _lines(tmp_path / "workflows.jsonl")[0]["wrote"] == "sweep"
    # Resumed, the same verdicts change nothing; a key judged before keeps its verdict
    assert record.main(tmp_path, _result(tmp_path, result)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [FINDING, swept]
    refuted = {**swept, "verdict": {**LIKE["verdict"], "confirmed": False}}
    # The candidate left unverified is judged in a second sweep, and is no longer waiting
    judged = {**later, "verdict": LIKE["verdict"]}
    again: dict[str, Any] = {**result, "records": [refuted, judged], "unverified": []}
    assert record.main(tmp_path, _result(tmp_path, again)) == 0
    assert _lines(tmp_path / "findings.jsonl") == [FINDING, swept, judged]
    assert _lines(tmp_path / "unverified.jsonl") == [DOD_GAP]


# The security lens's inventory (harness/surface.py)

POLICY = """# Security policy

## Scope

In scope is anything that breaks a promise, for example:

- **The token check:** a request that gets through without a valid access token.
- **The tool limits:**
  - reaching another company's data;
  - calling a tool the configuration doesn't offer.

Out of scope:

- ERPNext and Frappe themselves.
"""


def _vocabulary(tmp_path: Path, *promises: dict[str, Any]) -> list[dict[str, Any]]:
    (tmp_path / "SECURITY.md").write_text(POLICY, encoding="utf-8")
    return list(promises)


TOKEN = {"promise": "token-check", "source": "SECURITY.md", "text": "**The token check:**"}
COMPANY = {"promise": "one-company", "source": "SECURITY.md", "text": "another company's data"}
OFFERED = {"promise": "tools-offered", "source": "SECURITY.md", "text": "calling a tool"}


def test_the_policys_scope_is_its_bullets_without_those_that_only_head_others() -> None:
    assert surface.scope(POLICY) == [
        "**The token check:** a request that gets through without a valid access token.",
        "reaching another company's data;",
        "calling a tool the configuration doesn't offer.",
    ]


def test_a_vocabulary_that_follows_the_policy_is_kept(tmp_path: Path) -> None:
    assert surface.unkept(_vocabulary(tmp_path, TOKEN, COMPANY, OFFERED), tmp_path) == []


def test_a_line_of_the_policys_scope_without_a_promise_stops_the_inventory(
    tmp_path: Path,
) -> None:
    problems = surface.unkept(_vocabulary(tmp_path, TOKEN, COMPANY), tmp_path)
    assert problems == [
        "SECURITY.md: 0 promises for the line: calling a tool the configuration doesn't offer."
    ]


def test_a_line_of_the_policys_scope_with_two_promises_stops_the_inventory(
    tmp_path: Path,
) -> None:
    twice = {"promise": "tools", "source": "SECURITY.md", "text": "the configuration"}
    problems = surface.unkept(_vocabulary(tmp_path, TOKEN, COMPANY, OFFERED, twice), tmp_path)
    assert problems == [
        "SECURITY.md: 2 promises for the line: calling a tool the configuration doesn't offer."
    ]


def test_a_promise_whose_source_no_longer_holds_its_text_stops_the_inventory(
    tmp_path: Path,
) -> None:
    gone = {"promise": "fixed-schema", "source": "AGENTS.md", "text": "**Tools have a fixed"}
    nowhere = {**TOKEN, "promise": "token-again", "start": ["src/enterich/gone.py"]}
    problems = surface.unkept(
        _vocabulary(tmp_path, TOKEN, COMPANY, OFFERED, gone, nowhere), tmp_path
    )
    assert problems == [
        "fixed-schema: AGENTS.md doesn't hold its text",
        "token-again: src/enterich/gone.py doesn't exist",
        "SECURITY.md: 2 promises for the line: **The token check:** a request that gets through "
        "without a v",
    ]


def test_two_promises_of_one_name_stop_the_inventory(tmp_path: Path) -> None:
    problems = surface.unkept(_vocabulary(tmp_path, TOKEN, COMPANY, OFFERED, OFFERED), tmp_path)
    assert problems[0] == "tools-offered: two promises of this name"


def test_the_repositorys_vocabulary_follows_its_policy_and_its_specs() -> None:
    promises = surface._records(surface.PROMISES)  # pyright: ignore[reportPrivateUsage]
    assert surface.unkept(promises) == []
    known = {r.id for r in inventory.requirements()}
    assert {rid for p in promises for rid in p["requirements"]} <= known


def test_a_text_input_without_a_bound_is_found_by_its_path() -> None:
    schema = {
        "$defs": {
            "Row": {
                "properties": {
                    "account": {"type": "string", "maxLength": 140},
                    "debit": {"anyOf": [{"type": "number"}, {"type": "string"}, {"type": "null"}]},
                    "kind": {"type": "string", "enum": ["a", "b"]},
                }
            }
        },
        "properties": {
            "accounts": {"type": "array", "items": {"$ref": "#/$defs/Row"}},
            "posting_date": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
            "remarks": {"type": "string"},
            "name": {"type": "string", "pattern": "^x$"},
        },
    }
    assert surface.unbounded(schema) == ["accounts[].debit", "remarks"]


def _project(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "enterich"
    (src / "tools").mkdir(parents=True)
    (src / "erpnext.py").write_text(
        "class Erpnext:\n"
        "    async def insert(self, doctype, doc):\n"
        "        return await self._call('POST', _resource(doctype), {}, doc)\n"
        "    async def _call(self, method, path, params, body=None): ...\n",
        encoding="utf-8",
    )
    (src / "tools" / "drafts.py").write_text(
        "async def insert(context, doc):\n"
        "    line = {}\n"
        "    line.update(doc)\n"
        "    url = context.erpnext.geturl()\n"
        "    saved = await context.erpnext.insert('Journal Entry', line)\n"
        "    log.event('operation', sub=context.sub, **fields)\n"
        "    log.failure(exc, secrets, operation='x')\n"
        "    other.event('not the log')\n"
        "    return saved  # noqa: S104 - an example\n",
        encoding="utf-8",
    )
    (src / "config.py").write_text(
        "class Settings(BaseModel):\n"
        "    issuer: str\n"
        "    erpnext_api_key: SecretStr\n"
        "    max_drafts_per_hour: int | None = None\n"
        "    def secrets(self): ...\n"
        "class Other:\n"
        "    left_out: str\n",
        encoding="utf-8",
    )
    return tmp_path


def test_every_request_to_erpnext_is_listed_with_its_method_and_path(tmp_path: Path) -> None:
    assert surface.requests(_project(tmp_path)) == [
        {
            "at": "src/enterich/erpnext.py:3",
            "in": "insert",
            "method": "'POST'",
            "path": "_resource(doctype)",
        }
    ]


def test_only_calls_of_the_erpnext_clients_methods_are_client_calls(tmp_path: Path) -> None:
    # Neither a dict's update nor another attribute of the client
    assert surface.client_calls(_project(tmp_path)) == [
        {
            "at": "src/enterich/tools/drafts.py:5",
            "in": "insert",
            "call": "insert",
            "first": "'Journal Entry'",
        }
    ]


def test_every_log_call_is_listed_with_its_event_and_fields(tmp_path: Path) -> None:
    assert surface.log_calls(_project(tmp_path)) == [
        {
            "at": "src/enterich/tools/drafts.py:6",
            "in": "insert",
            "call": "event",
            "event": "operation",
            "fields": ["sub", "**"],
        },
        {
            "at": "src/enterich/tools/drafts.py:7",
            "in": "insert",
            "call": "failure",
            "event": None,
            "fields": ["operation"],
        },
    ]


def test_the_settings_are_the_fields_of_the_configurations_class(tmp_path: Path) -> None:
    assert surface.settings(_project(tmp_path)) == [
        {"setting": "issuer", "type": "str"},
        {"setting": "erpnext_api_key", "type": "SecretStr"},
        {"setting": "max_drafts_per_hour", "type": "int | None"},
    ]


def test_a_silenced_security_rule_is_listed_as_written(tmp_path: Path) -> None:
    assert surface.silenced(_project(tmp_path)) == [
        {
            "at": "src/enterich/tools/drafts.py:9",
            "line": "return saved  # noqa: S104 - an example",
        }
    ]


def test_the_security_inventory_of_the_repository_is_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert surface.main(tmp_path) == 0
    counts = json.loads(capsys.readouterr().out)
    promises = [json.loads(line) for line in (tmp_path / "promises.jsonl").read_text().splitlines()]
    found = json.loads((tmp_path / "surface.json").read_text())
    assert counts["promises"] == len(promises) > 0
    # Each promise carries its requirements in full: the token check's, with its tests
    check = next(p for p in promises if p["promise"] == "token-check")
    by_id = {r["id"]: r for r in check["requirements"]}
    assert by_id["REQ-002-PRS-NF001"]["dod"]
    assert by_id["REQ-002-PRS-NF001"]["tests"]
    # Every tool of the snapshot, the three writes among the requests
    assert counts["tools"] == len(json.loads((inventory.ROOT / surface.TOOLS).read_text()))
    assert {r["method"] for r in found["requests"]} == {"'GET'", "'POST'", "'PUT'"}
    assert [r["in"] for r in found["requests"] if r["method"] != "'GET'"] == [
        "insert",
        "update",
        "add_comment",
    ]


# The security lens's findings in triage and the plan

BREACH: dict[str, Any] = {
    "kind": "breach",
    "promise": "one-company",
    "location": "src/enterich/tools/drafts.py:editable",
    "requirement": "REQ-001-PRS-F007",
    "mutants": [],
    "claim": "An update reaches a draft of another company",
    "evidence": "drafts.py:92 reads the company after the write",
    "proposal": "Check the company before the write",
    "origin": "promise:one-company",
    "verdict": {
        "confirmed": True,
        "class": "fix",
        "pattern": None,
        "test_files": ["tests/integration/test_service.py"],
        "reproduction": "A throwaway test against the fake: the update of OTHER-1 was sent",
        "reason": "reproduced",
    },
}
UNPROVEN: dict[str, Any] = {
    **BREACH,
    "kind": "unproven",
    "claim": "No test would notice an update without the company check",
    "verdict": {**BREACH["verdict"], "reproduction": None},
}


@pytest.mark.parametrize(
    ("name", "lens"),
    [
        ("2026-11-14-tests", "tests"),
        ("2026-11-14-tests-2", "tests"),
        ("2026-11-15-security", "security"),
        ("2026-11-15-security-2", "security"),
        # The first lens, if the name says none
        ("run", "tests"),
    ],
)
def test_a_runs_lens_is_in_its_directorys_name(name: str, lens: str) -> None:
    assert triage.lens(Path("harness/runs") / name) == lens


def test_a_security_findings_key_names_its_promise() -> None:
    """One function can break two promises: two findings, two suppressions."""
    assert triage.key(BREACH) == "breach:one-company:src/enterich/tools/drafts.py:editable"
    assert triage.key(UNPROVEN) == "unproven:one-company:src/enterich/tools/drafts.py:editable"
    assert triage.slug(BREACH) == "one-company-drafts-editable"


def test_a_complete_security_record_can_be_triaged() -> None:
    assert triage.check(BREACH, promises={"one-company"}) == []
    assert triage.check(UNPROVEN, promises={"one-company"}) == []


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        ({**BREACH, "promise": None}, "promise None"),
        ({**BREACH, "promise": "be-nice"}, "promise 'be-nice'"),
        # A breach is confirmed only as reproduced
        ({**BREACH, "verdict": {**BREACH["verdict"], "reproduction": None}}, "reproduction"),
        ({**BREACH, "verdict": {**BREACH["verdict"], "reproduction": " "}}, "reproduction"),
        # A tests finding names no promise
        ({**FINDING, "promise": "one-company"}, "promise 'one-company'"),
    ],
)
def test_a_security_record_with_a_wrong_field_is_refused(
    record: dict[str, Any], problem: str
) -> None:
    assert any(problem in p for p in triage.check(record, promises={"one-company"}))


def test_a_refuted_breach_needs_no_reproduction() -> None:
    verdict = {**BREACH["verdict"], "confirmed": False, "class": "drop", "reproduction": None}
    assert triage.check({**BREACH, "verdict": verdict}, promises={"one-company"}) == []


def _security_run(tmp_path: Path) -> Path:
    run = tmp_path / "2026-11-15-security"
    run.mkdir()
    return run


def test_triage_reports_a_security_run_by_its_own_kinds(tmp_path: Path) -> None:
    run = _security_run(tmp_path)
    promises = _write(tmp_path / "promises.jsonl", [{"promise": "one-company"}])
    _write(run / "findings.jsonl", [BREACH, UNPROVEN])
    empty = _write(tmp_path / "empty.jsonl", [])
    done = triage.main(
        run, suppressions=empty, backlog=tmp_path / "backlog", patterns=empty, promises=promises
    )
    assert done == 0
    report = (run / "report.md").read_text()
    assert report.startswith("# Security lens: 2026-11-15-security\n")
    assert "| breach | 1 | 1 |" in report
    assert "| unproven | 1 | 1 |" in report
    assert "mutant-gap" not in report
    # No survivors.jsonl in a security run: a fix has no diffs
    assert [(f["key"], f["diffs"]) for f in _lines(run / "fixes.jsonl")] == [
        (triage.key(BREACH), {}),
        (triage.key(UNPROVEN), {}),
    ]


def test_a_finding_of_another_lens_is_refused_in_a_run(tmp_path: Path) -> None:
    run = _security_run(tmp_path)
    promises = _write(tmp_path / "promises.jsonl", [{"promise": "one-company"}])
    _write(run / "findings.jsonl", [FINDING])
    empty = _write(tmp_path / "empty.jsonl", [])
    done = triage.main(
        run, suppressions=empty, backlog=tmp_path / "backlog", patterns=empty, promises=promises
    )
    assert done == 1


def test_a_security_runs_branches_are_named_after_its_lens() -> None:
    fix = {**BREACH, "key": triage.key(BREACH), "slug": triage.slug(BREACH), "ratchet": None}
    [group] = plan.groups([fix], [], lens="security")
    assert group["branch"] == "auto/security-integration-service"
    [group] = plan.groups([fix], [])
    assert group["branch"] == "auto/tests-integration-service"
