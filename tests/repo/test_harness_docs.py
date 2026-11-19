"""The docs lens's deterministic stages (ADR-008): its inventory follows the documents in
the repository, and triage takes a drift only with what shows it."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from harness import documents, plan, triage


def _tree(root: Path, *files: str) -> Path:
    for name in files:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("text\n", encoding="utf-8")
    return root


GUIDE = {
    "promise": "guide",
    "documents": ["docs/guides/a.md"],
    "against": ["src/enterich"],
    "asks": "Does it do what the guide says?",
}
SPECS = {
    "promise": "specs",
    "documents": ["docs/specs"],
    "against": ["src/enterich/tools"],
    "asks": "Does it do what the specs say?",
}
OUT = {"promise": "readme", "documents": ["README.md"], "against": [], "out": "not now"}
FILES = ("README.md", "docs/guides/a.md", "docs/specs/req-001.md", "src/enterich/tools/x.py")


def test_a_vocabulary_that_holds_each_document_once_is_kept(tmp_path: Path) -> None:
    assert documents.unkept([GUIDE, SPECS, OUT], _tree(tmp_path, *FILES)) == []


def test_a_document_in_no_record_stops_the_inventory(tmp_path: Path) -> None:
    root = _tree(tmp_path, *FILES, "docs/guides/b.md", "docs/arc42/adr/ADR-001.md")
    assert documents.unkept([GUIDE, SPECS, OUT], root) == [
        "docs/arc42/adr/ADR-001.md: in no record",
        "docs/guides/b.md: in no record",
    ]


def test_a_document_in_two_records_stops_the_inventory(tmp_path: Path) -> None:
    twice = {**SPECS, "promise": "spec", "documents": ["docs/specs/req-001.md"]}
    assert documents.unkept([GUIDE, SPECS, OUT, twice], _tree(tmp_path, *FILES)) == [
        "docs/specs/req-001.md: in 2 records"
    ]


def test_a_path_that_doesnt_exist_or_a_name_twice_stops_the_inventory(tmp_path: Path) -> None:
    gone = {**GUIDE, "against": ["src/enterich/gone.py"]}
    assert documents.unkept([gone, SPECS, OUT, OUT], _tree(tmp_path, *FILES)) == [
        "readme: two records of this name",
        "guide: src/enterich/gone.py doesn't exist",
        "README.md: in 2 records",
    ]


def test_a_record_surveyed_says_what_it_asks_and_one_left_out_why(tmp_path: Path) -> None:
    unsaid = {**SPECS, "asks": " "}
    reasonless = {**OUT, "out": ""}
    assert documents.unkept([GUIDE, unsaid, reasonless], _tree(tmp_path, *FILES)) == [
        "specs: says nothing it asks",
        "readme: says no reason it is left out",
    ]


def test_the_repositorys_vocabulary_holds_each_of_its_documents_once() -> None:
    assert documents.unkept(documents.vocabulary()) == []


def test_a_document_is_touched_by_a_change_to_it_or_to_what_it_is_read_against() -> None:
    records = [GUIDE, SPECS, OUT]
    assert documents.touched(records, ["docs/guides/a.md"]) == ["guide"]
    assert documents.touched(records, ["src/enterich/tools/x.py"]) == ["guide", "specs"]
    assert documents.touched(records, ["docs/specs/req-001.md"]) == ["specs"]
    # A record left out is never surveyed, and a sibling's name is no path under a start
    assert documents.touched(records, ["README.md", "src/enterich_old.py"]) == []


def test_the_docs_inventory_writes_the_records_it_surveys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert documents.main(tmp_path) == 0
    written = [json.loads(line) for line in (tmp_path / "documents.jsonl").read_text().splitlines()]
    surveyed = [r["promise"] for r in documents.vocabulary() if not r.get("out")]
    assert [r["promise"] for r in written] == surveyed
    assert not (tmp_path / "since.json").exists()
    assert json.loads(capsys.readouterr().out) == {"documents": len(surveyed)}


def test_a_docs_inventory_since_a_commit_names_what_changed_and_the_records_touched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert documents.main(tmp_path, since="HEAD") == 0
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 - git from PATH, as in CI
        cwd=documents.ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    since = json.loads((tmp_path / "since.json").read_text())
    assert since == {"commit": head, "changed": [], "documents": []}
    assert json.loads(capsys.readouterr().out)["touched"] == 0


def test_a_vocabulary_that_isnt_kept_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(documents, "vocabulary", lambda: [GUIDE])
    assert documents.main(tmp_path / "run") == 1
    assert not (tmp_path / "run").exists()


# The docs lens's findings in triage and the plan

DRIFT: dict[str, Any] = {
    "kind": "drift",
    "promise": "configuration-guide",
    "location": "docs/guides/configuration.md:ENTERICH_PORT",
    "requirement": "REQ-002-PRS-NF005",
    "mutants": [],
    "claim": "The guide gives the port as 8001; Enterich listens on 8000",
    "evidence": "configuration.md:40 says 8001; config.py:88 defaults to 8000",
    "proposal": "Give the port as 8000",
    "origin": "document:configuration-guide",
    "verdict": {
        "confirmed": True,
        "class": "fix",
        "pattern": None,
        "test_files": [],
        "reproduction": "configuration.md:40 `8001`; config.py:88 `port: int = 8000`",
        "reason": "both lines read",
    },
}


def test_a_docs_run_is_in_its_directorys_name() -> None:
    assert triage.lens(Path("harness/runs/2026-11-17-docs")) == "docs"
    assert triage.LENSES["docs"] == {"drift"}


def test_a_drifts_key_names_its_document_and_place() -> None:
    assert triage.key(DRIFT) == (
        "drift:configuration-guide:docs/guides/configuration.md:ENTERICH_PORT"
    )
    assert triage.slug(DRIFT) == "configuration-guide-configuration-enterich-port"


def test_a_complete_drift_can_be_triaged() -> None:
    assert triage.check(DRIFT, promises={"configuration-guide"}) == []


@pytest.mark.parametrize(
    ("record", "problem"),
    [
        ({**DRIFT, "promise": None}, "promise None"),
        ({**DRIFT, "promise": "token-check"}, "promise 'token-check'"),
        # A drift is confirmed only with both sides shown
        ({**DRIFT, "verdict": {**DRIFT["verdict"], "reproduction": None}}, "reproduction"),
    ],
)
def test_a_drift_with_a_wrong_field_is_refused(record: dict[str, Any], problem: str) -> None:
    assert any(problem in p for p in triage.check(record, promises={"configuration-guide"}))


def test_each_lens_with_promises_reads_its_own_vocabulary() -> None:
    assert triage.VOCABULARIES == {
        "security": triage.PROMISES,
        "docs": documents.DOCUMENTS,
        "code": triage.MODULES,
    }
    assert triage.DOCUMENTS == documents.DOCUMENTS


def test_triage_reports_a_docs_run_by_its_kind(tmp_path: Path) -> None:
    run = tmp_path / "2026-11-17-docs"
    run.mkdir()
    vocabulary = tmp_path / "documents.jsonl"
    vocabulary.write_text(json.dumps({"promise": "configuration-guide"}) + "\n")
    (run / "findings.jsonl").write_text(json.dumps(DRIFT) + "\n")
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    done = triage.main(
        run, suppressions=empty, backlog=tmp_path / "backlog", patterns=empty, promises=vocabulary
    )
    assert done == 0
    report = (run / "report.md").read_text()
    assert report.startswith("# Docs lens: 2026-11-17-docs\n")
    assert "| drift | 1 | 1 |" in report


def test_a_docs_runs_branches_are_named_after_its_lens() -> None:
    fix = {**DRIFT, "key": triage.key(DRIFT), "slug": triage.slug(DRIFT), "ratchet": None}
    [group] = plan.groups([fix], [], lens="docs")
    # A fix of a document changes no test file: its branch is named after its survey
    assert group["branch"] == "auto/docs-document-configuration-guide"
