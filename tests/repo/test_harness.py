"""The improvement pipeline's deterministic stages (ADR-008): the inventory reads the specs
and tests as they are written, and triage refuses a record it can't trust."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness import gate, inventory, mutation, triage


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


def test_every_id_a_test_cites_is_in_a_spec() -> None:
    known = {r.id for r in inventory.requirements()}
    cited = {i for t in inventory.tests() for i in (*t.ids, *t.section_ids)}
    assert cited <= known


def test_the_inventory_leaves_out_the_harness_tests() -> None:
    """They cite requirement IDs as data, not as what they check."""
    assert not any(t.id.startswith("tests/repo/test_harness.py") for t in inventory.tests())


MUTANT = "enterich.shapes.x_to_text__mutmut_6"
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
    return triage.main(run, suppressions=suppressions, backlog=run / "backlog")


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


def test_triage_hands_the_fix_stage_each_fix_with_its_mutants(tmp_path: Path) -> None:
    survivor = {"id": MUTANT, "module": "enterich.shapes", "filter": None, "diff": "-a\n+b"}
    _write(tmp_path / "survivors.jsonl", [survivor])
    proposal = {**DOD_GAP, "verdict": {**FINDING["verdict"], "class": "proposal"}}
    assert _triage(tmp_path, [FINDING, proposal]) == 0
    fixes = [json.loads(line) for line in (tmp_path / "fixes.jsonl").read_text().splitlines()]
    assert [(f["key"], f["slug"]) for f in fixes] == [(triage.key(FINDING), "shapes-to-text-6")]
    # A mutant gone from survivors.jsonl has no diff to hand over
    assert fixes[0]["diffs"] == {MUTANT: "-a\n+b"}


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


@pytest.mark.parametrize(
    ("diff", "kind"),
    [
        # A message's wording: noise
        (
            '-    raise Refusal("The draft is gone.")\n+    raise Refusal("the draft is gone.")',
            "message",
        ),
        ('-    log.info("call failed")\n+    log.info("XXcall failedXX")', "message"),
        # Type text in cast() is never checked at runtime: equivalent
        ('-    rows = cast("list[Any]", value)\n+    rows = cast("LIST[ANY]", value)', "cast"),
        # A field name or key changes behaviour: for the agents
        ('-    return doc.get("name")\n+    return doc.get("XXnameXX")', None),
        ("-    if 300 <= status < 400:\n+    if 300 < status < 400:", None),
        # A message changed along with code: for the agents
        (
            '-    raise Refusal("Too many.") if n > 1 else None\n'
            '+    raise Refusal("too many.") if n >= 1 else None',
            None,
        ),
    ],
)
def test_survivors_a_script_can_judge_are_filtered(diff: str, kind: str | None) -> None:
    """ADR-008: only what no caller can observe is left out of the agents' survey."""
    assert mutation.filtered(diff) == kind


TESTS_ONLY = ["tests/unit/test_shapes.py"]


def test_a_fix_branch_with_a_test_first_passes_the_gate() -> None:
    subjects = ["test: a page of exactly limit records has no more", "fix: has_more at the limit"]
    paths = [*TESTS_ONLY, "src/enterich/shapes.py", "CHANGELOG.md"]
    assert gate.problems("auto/tests-page-limit", subjects, paths) == []


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
