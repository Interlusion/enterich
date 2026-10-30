"""The release notes from CHANGELOG.md (scripts/changelog.py, used by release.yml)."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "changelog.py"
CHANGELOG = """# Changelog

Intro.

## [Unreleased]

### Added

- Next thing.

## [0.2.0] - 2026-12-01

### Added

- A tool.

### Rights

- Item read.

## [0.1.1] - 2026-11-15 [YANKED]

### Fixed

- A broken fix.

## [0.1.0] - 2026-11-01

### Added

- The first tools.

[Unreleased]: https://github.com/interlusion/enterich/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/interlusion/enterich/compare/v0.1.0...v0.2.0
"""


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("changelog", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


changelog = load()


@pytest.mark.parametrize(
    ("name", "notes"),
    [
        ("0.2.0", "### Added\n\n- A tool.\n\n### Rights\n\n- Item read."),
        ("0.1.0", "### Added\n\n- The first tools."),
        ("0.1.1", "### Fixed\n\n- A broken fix."),
        ("Unreleased", "### Added\n\n- Next thing."),
        ("0.3.0", None),
        ("0.2", None),
        ("0x1x0", None),  # the dots are literal
    ],
)
def test_a_section_is_its_body_up_to_the_next_heading_or_the_links(
    name: str, notes: str | None
) -> None:
    assert changelog.section(CHANGELOG, name) == notes


def test_an_empty_section_counts_as_none() -> None:
    assert changelog.section("## [0.1.0] - 2026-11-01\n\n## [0.0.1]\n", "0.1.0") is None


@pytest.fixture
def file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(CHANGELOG)
    monkeypatch.setattr(changelog, "CHANGELOG", path)
    return path


@pytest.mark.usefixtures("file")
def test_the_notes_of_a_release(capsys: pytest.CaptureFixture[str]) -> None:
    assert changelog.main(["0.1.0"]) == 0
    assert capsys.readouterr().out == "### Added\n\n- The first tools.\n"


@pytest.mark.usefixtures("file")
def test_a_release_without_its_section_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert changelog.main(["0.3.0"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "no section `## [0.3.0]`" in captured.err


@pytest.mark.usefixtures("file")
def test_a_draft_falls_back_to_unreleased(capsys: pytest.CaptureFixture[str]) -> None:
    assert changelog.main(["0.3.0", "--draft"]) == 0
    captured = capsys.readouterr()
    assert captured.out == "### Added\n\n- Next thing.\n"
    assert "draft uses Unreleased" in captured.err


@pytest.mark.usefixtures("file")
def test_a_draft_uses_the_versions_section_when_there_is_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert changelog.main(["0.2.0", "--draft"]) == 0
    captured = capsys.readouterr()
    assert captured.out.startswith("### Added\n\n- A tool.")
    assert captured.err == ""


def test_a_draft_without_either_section_is_refused(
    file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    file.write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - 2026-11-01\n\n- First.\n")
    assert changelog.main(["0.2.0", "--draft"]) == 1
    captured = capsys.readouterr()
    assert "draft uses Unreleased" not in captured.err
    assert "no section `## [0.2.0]`" in captured.err


@pytest.mark.parametrize("argv", [[], ["0.1.0", "--final"], ["0.1.0", "--draft", "x"]])
def test_other_arguments_are_refused(argv: list[str]) -> None:
    assert changelog.main(argv) == 2


def test_the_real_changelog_keeps_its_unreleased_heading() -> None:
    # Empty right after a release, so only the heading is required.
    assert "\n## [Unreleased]\n" in changelog.CHANGELOG.read_text()
