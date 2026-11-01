# ITEM-005: Draft updates only on the agent's own drafts

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | improvement |
| **Origin** | [Analysis 001](../analysis/analysis-001-excessive-agency-review.md#35-write-operations), finding 1 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |

## Summary

Let the update operations change only drafts the agent user created, and answer any other draft as unknown, so that an agent steered by outside text can't rewrite a draft a person prepared and is about to submit.

## Context

The update operations check that a draft belongs to the assigned company, is still a draft and hasn't changed since it was read ([REQ-001-PRS-F003](../specs/req-001-core.md#req-001-prs-f003-draft-update-operations), [REQ-001-PRS-F004](../specs/req-001-core.md#req-001-prs-f004-stale-updates-refused)); they don't check who created it. A bookkeeper's draft purchase invoice can thus get other rates, rows, due date, `bill_no` or accounts from the agent. ERPNext's version history records the change, but nothing points the bookkeeper to it: Enterich adds a comment only when there are warnings.

The use case for updates is correcting the agent's own drafts, after a review remark or a lost answer; changing a person's draft isn't among the user stories.

## Conditions

- REQ-001 first: [REQ-001-PRS-F003](../specs/req-001-core.md#req-001-prs-f003-draft-update-operations) adds "created by the agent user", with a Definition of Done case for a person's draft refused without a write. Then tests, then code (`editable()` in `src/enterich/tools/drafts.py`).
- A person's draft answers as unknown or unpermitted ([REQ-001-PRS-F009](../specs/req-001-core.md#req-001-prs-f009-unknown-or-unpermitted-names)), like another company's: the agent learns nothing about it.
- The reviewing guide says that the agent changes only its own drafts.

## Open Questions

- How Enterich learns the agent user's name: once at start through a fixed call (Frappe's whitelisted `frappe.auth.get_logged_user`), or a configuration variable that must match the key. The first can't drift; it adds one call at start, and a start that fails while ERPNext is down. [ITEM-008](item-008-write-ceilings.md) needs the same name.
- Is a switch for sites that want the agent to change any draft worth its weight, or is the narrow rule enough?
- Can ERPNext enforce it too: a permission rule "only if creator" on write for the agent's role? That would make it part of the ceiling, not only Enterich's code; check what it does to the agent's comments and to drafts a person then edits.
