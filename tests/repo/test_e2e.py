"""The end-to-end tests' setup agrees with the specs and with itself (ITEM-004)."""

import re
from pathlib import Path

from enterich import tools
from tests.e2e.seed import RIGHTS, Rights
from tests.readme import AREAS

ROOT = Path(__file__).parent.parent.parent
AREA_SPECS = sorted(
    p for p in (ROOT / "docs" / "specs").glob("req-00[3-9]-*.md") if ".history" not in p.name
)
ROW = re.compile(r"^\| ((?:`[a-z_]+`(?:, )?)+) \| (.+) \|$")
REPORT = re.compile(r"the role added to the (.+) report")


def spec_rights(specs: list[Path] = AREA_SPECS) -> list[Rights]:
    """Each row of the specs' Rights sections, read as RIGHTS writes it."""
    rows: list[Rights] = []
    for spec in specs:
        section = spec.read_text().split("### Rights", 1)[1].split("\n#", 1)[0]
        for line in section.splitlines():
            match = ROW.match(line)
            if not match:
                continue
            operations = tuple(re.findall(r"`([a-z_]+)`", match[1]))
            doctypes: dict[str, tuple[str, ...]] = {}
            reports: list[str] = []
            # Remarks in parentheses explain a right; they may hold semicolons.
            for part in re.sub(r" \([^)]*\)", "", match[2]).split(";"):
                part = part.strip()
                if report := REPORT.fullmatch(part):
                    reports.append(report[1])
                    continue
                names, rights = part.split(": ")
                for name in names.split(", "):
                    doctypes[name] = tuple(rights.split(", "))
            rows.append(Rights(operations, doctypes, tuple(reports)))
    return rows


def normalised(rows: tuple[Rights, ...] | list[Rights]) -> list[tuple[object, ...]]:
    return [
        (r.operations, {d: frozenset(p) for d, p in r.doctypes.items()}, r.reports) for r in rows
    ]


def test_the_seeded_rights_are_the_specs_rights() -> None:
    """The agent user is seeded with RIGHTS, so RIGHTS must say what the specs say
    (REQ-002-PRS-NF013); a changed Rights section fails here until RIGHTS follows."""
    assert AREA_SPECS
    assert normalised(RIGHTS) == normalised(spec_rights())


def test_each_operation_has_one_rights_row_in_its_area_spec() -> None:
    """The end-to-end rights tests run the specs' rows, so an operation without a row
    would go unproven (REQ-002-PRS-NF013)."""
    listed = sorted(op for row in spec_rights() for op in row.operations)
    assert listed == list(tools.names())
    for module, spec in AREAS:
        rows = spec_rights([ROOT / "docs" / "specs" / spec])
        assert {op for row in rows for op in row.operations} == {
            op.name for op in module.OPERATIONS
        }, spec


def test_the_erpnext_services_run_one_image() -> None:
    """The image is written out in each service for Dependabot; an edit by hand must
    not leave two versions."""
    compose = (ROOT / "tests" / "e2e" / "compose.yml").read_text()
    images = re.findall(r"^    image: (frappe/erpnext:\S+)$", compose, re.MULTILINE)
    assert len(images) == 3
    assert len(set(images)) == 1
