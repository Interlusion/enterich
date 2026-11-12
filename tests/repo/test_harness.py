"""The improvement pipeline's deterministic stages (ADR-008): the inventory reads the specs
and tests as they are written, and triage refuses a record it can't trust."""

import json
from pathlib import Path
from typing import Any

import pytest

from harness import inventory, mutation, triage


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


FINDING: dict[str, Any] = {
    "key": "mutant-gap:src/enterich/shapes.py:to_text",
    "kind": "mutant-gap",
    "location": "src/enterich/shapes.py:to_text",
    "requirement": "REQ-001-PRS-NF003",
    "claim": "No test notices non-ASCII text escaped",
    "evidence": "mutant to_text_6 survives",
    "proposal": "A result with umlauts keeps them and counts them once",
    "verdict": {"confirmed": True, "class": "fix", "reason": "reproduced"},
}


def test_a_complete_record_can_be_triaged() -> None:
    assert triage.check(FINDING) == []


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"kind": "opinion"}, "kind 'opinion'"),
        ({"claim": None}, "claim missing"),
        ({"verdict": {"confirmed": "yes", "class": "fix", "reason": "r"}}, "not a boolean"),
        ({"verdict": {"confirmed": True, "class": "merge", "reason": "r"}}, "verdict.class"),
        ({"verdict": None}, "verdict missing"),
    ],
)
def test_a_record_with_a_wrong_field_is_refused(change: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in triage.check({**FINDING, **change}))


def test_triage_writes_no_report_from_a_bad_record(tmp_path: Path) -> None:
    lines = [FINDING, {**FINDING, "key": "k2", "kind": "opinion"}]
    (tmp_path / "findings.jsonl").write_text("\n".join(json.dumps(r) for r in lines))
    assert triage.main(tmp_path) == 1
    assert not (tmp_path / "report.md").exists()


def test_triage_reports_confirmed_findings_by_class(tmp_path: Path) -> None:
    refuted = {**FINDING, "key": "k2", "verdict": {**FINDING["verdict"], "confirmed": False}}
    (tmp_path / "findings.jsonl").write_text(f"{json.dumps(FINDING)}\n{json.dumps(refuted)}\n")
    assert triage.main(tmp_path) == 0
    report = (tmp_path / "report.md").read_text()
    assert "| all | 2 | 1 |" in report
    assert "## Fix (1)" in report
    assert "## Proposal (0)" in report


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
