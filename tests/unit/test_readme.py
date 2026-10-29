"""The README lists every tool of the tool-list snapshot (ITEM-001)."""

from pathlib import Path

import pytest

from tests import readme

BLOCK = f"{readme.START}\nold\n{readme.END}"


def test_the_readme_lists_the_tools_of_the_snapshot() -> None:
    assert readme.current() == readme.render(), (
        "The README's tool list differs from tests/snapshots/tools.json; "
        "write it with `uv run python -m tests.readme` and review the diff."
    )


def test_writing_replaces_only_the_block(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    file = tmp_path / "README.md"
    file.write_text(f"# Erpel\n\n{BLOCK}\n\n## Documentation\n")
    monkeypatch.setattr(readme, "README", file)
    readme.write()
    assert file.read_text() == f"# Erpel\n\n{readme.render()}\n\n## Documentation\n"


@pytest.mark.parametrize(
    "text",
    [
        "# Erpel\n",
        f"`{readme.END}` ends it.\n\n{BLOCK}\n",
        f"{BLOCK}\n\n{BLOCK}\n",
        f"{readme.END}\n{readme.START}\n",
    ],
)
def test_markers_out_of_place_change_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str
) -> None:
    file = tmp_path / "README.md"
    file.write_text(text)
    monkeypatch.setattr(readme, "README", file)
    with pytest.raises(ValueError, match="needs one"):
        readme.write()
    assert file.read_text() == text
