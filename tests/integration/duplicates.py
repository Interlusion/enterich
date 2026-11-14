"""The refusal and the warning of a duplicate draft (REQ-001-PRS-F005), in full, for every
draft's tests: a test compares the whole text, so it notices a kind or a match that is
wrong or missing, not only the start and the other document's name. The texts are written
out here, not taken from `drafts.refuse_duplicates` and `drafts.duplicate_warning`, so a
change to the helpers' wording or default shows too."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Duplicate:
    """What a duplicate is of (`kind`) and what matched (`match`), as the tool names them."""

    kind: str
    match: str

    def refusal(self, found: str) -> str:
        return (
            f"allow_duplicate: a {self.kind} with the same {self.match} exists ({found}). "
            "Check it first; to create another anyway, repeat with allow_duplicate true."
        )

    def warning(self, found: str) -> str:
        return f"Possible duplicate of {found}: a {self.kind} with the same {self.match}."
