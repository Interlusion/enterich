# REQ-001 Decision Log

A curated log of substantive changes to REQ-001. The current authoritative state always lives in [`req-001-core.md`](./req-001-core.md). This file records *why* the spec evolved — useful for context that git-blame alone can't surface (intent, alternatives considered, links to PRs and ADRs).

Entries are most-recent first.

## 2026-10-30 — Amending is a door the role doesn't close

- **Status:** Accepted (integrated into REQ-001)
- **Change:** REQ-001-URS-F003's rationale no longer counts amend among what ERPNext's role refuses and names the amendment among the doors; REQ-001-PRS-F006's Definition of Done adds `amended_from` to what no ERPNext call of Enterich's carries.
- **Why:** The end-to-end test of the ceiling (ITEM-004) showed the agent user's key, without the amend right, creating an amendment of a cancelled document: Frappe checks create when it saves a document with `amended_from`, and uses the amend right only for the form's Amend button. The requirement stays as it was: Enterich offers no input that reaches `amended_from`, so only the rationale's account of ERPNext was wrong.
- **Trade-offs / out-of-scope:** The deployment's role still withholds amend (REQ-001's assumptions, the configuration guide): it keeps the form's button away from the agent user, though it closes no REST door.
- **Affected sections:** URS — Functional (REQ-001-URS-F003), PRS — Functional (REQ-001-PRS-F006).
- **Refs:** `tests/e2e/test_ceiling.py`; [ITEM-004](../backlog/item-004-real-erpnext-test.md).
