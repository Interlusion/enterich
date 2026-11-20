"""The refusal and the warning of a duplicate draft (REQ-001-PRS-F005), in full, for every
draft's tests: a test compares the whole text, so it notices a kind or a match that is
wrong or missing, not only the start and the other document's name. The texts are written
out here, not taken from `drafts.refuse_duplicates` and `drafts.duplicate_warning`, so a
change to the helpers' wording or default shows too."""

from dataclasses import dataclass
from typing import Any

import pytest

from enterich.erpnext import Erpnext, ErpnextError
from enterich.tools import drafts

FAILED_RESULT = (
    "ERPNext saved the draft, but Enterich couldn't build the rest of this result (ERPNext "
    "refused a later read). Read the draft to see it."
)


@dataclass(frozen=True)
class Duplicate:
    """What a duplicate is of (`kind`) and what matched (`match`), as the tool names them."""

    kind: str
    match: str

    def refusal(self, found: str) -> str:
        return refusal((self, found))

    def warning(self, found: str) -> str:
        return f"Possible duplicate of {found}: a {self.kind} with the same {self.match}."


def refusal(*matches: tuple[Duplicate, str]) -> str:
    """The refusal of a create that matched each of `matches` (what, and the documents found),
    naming them all."""
    exists = ", and ".join(
        f"a {what.kind} with the same {what.match} exists ({found})" for what, found in matches
    )
    them = "it" if len(matches) == 1 else "them"
    return (
        f"allow_duplicate: {exists}. Check {them} first; to create another anyway, repeat with "
        "allow_duplicate true."
    )


def capped(rows: int) -> str:
    """The warning of a duplicate check that read as many rows as it reads at most."""
    return (
        f"Enterich's duplicate check read only the first {rows:,} rows of the drafts it "
        "compares with, so a duplicate among further drafts may have gone unnoticed."
    )


def bounded(monkeypatch: pytest.MonkeyPatch, rows: int) -> None:
    """Every duplicate check that compares rows reads at most `rows` of them."""
    monkeypatch.setattr(drafts, "MAX_DUPLICATE_ROWS", rows)


def failing_after_the_write(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every insert and update fails right after ERPNext saved the draft, as a later read of the
    operation would: the result is the fallback of REQ-001-PRS-F015, whose warnings start with
    those known before the write."""
    for method in ("insert", "update"):
        original = getattr(Erpnext, method)

        async def failing(self: Erpnext, *args: Any, _original: Any = original) -> Any:
            await _original(self, *args)
            raise ErpnextError("ERPNext refused a later read.")

        monkeypatch.setattr(Erpnext, method, failing)
