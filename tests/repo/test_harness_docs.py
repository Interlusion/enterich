"""The docs lens's deterministic stages (ADR-008): its inventory follows the documents in
the repository."""

import json
import subprocess
from pathlib import Path

import pytest

from harness import documents


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
