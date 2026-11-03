# ITEM-005: Draft updates only on the agent's own drafts

| Meta | Value |
| :- | :- |
| **Status** | IMPLEMENTED |
| **Type** | improvement |
| **Origin** | [Analysis 001](../../analysis/analysis-001-excessive-agency-review.md#35-write-operations), finding 1 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |
| **Implemented** | 2026-11-02; comes with the release after v0.2.1 |

## Summary

Let the update operations change only drafts the agent user created, and refuse any other draft, so that an agent steered by outside text can't rewrite a draft a person prepared and is about to submit.

## Context

The update operations check that a draft belongs to the assigned company, is still a draft and hasn't changed since it was read ([REQ-001-PRS-F003](../../specs/req-001-core.md#req-001-prs-f003-draft-update-operations), [REQ-001-PRS-F004](../../specs/req-001-core.md#req-001-prs-f004-stale-updates-refused)); they don't check who created it. A bookkeeper's draft purchase invoice can thus get other rates, rows, due date, `bill_no` or accounts from the agent. ERPNext's version history records the change, but nothing points the bookkeeper to it: Enterich adds a comment only when there are warnings.

The use case for updates is correcting the agent's own drafts, after a review remark or a lost answer; changing a person's draft isn't among the user stories.

## Conditions

- REQ-001 first: [REQ-001-PRS-F003](../../specs/req-001-core.md#req-001-prs-f003-draft-update-operations) adds "created by the agent user", with a Definition of Done case for a person's draft refused without a write. Then tests, then code (`editable()` in `src/enterich/tools/drafts.py`).
- A person's draft gets a refusal of its own, naming the rule, not the unknown-name answer of [REQ-001-PRS-F009](../../specs/req-001-core.md#req-001-prs-f009-unknown-or-unpermitted-names): the agent can read the draft and its `owner` through the get and list operations, so "doesn't exist" would contradict what it just read.
- The reviewing guide says that the agent changes only its own drafts.

## Open Questions

None. Decided on 2026-11-02:

- **The agent user's name** comes from `frappe.auth.get_logged_user`, asked at the first update and kept until Enterich stops, not at start: it can't drift from the key, and a start doesn't depend on ERPNext. A failed answer isn't kept. [ITEM-008](item-008-write-ceilings.md) uses the same name.
- **A draft of the agent's that a person edited stays updatable**, after a re-read (stale check): the agent can then overwrite a correction, which the reviewing guide points out. Locking a draft once a person changed it (`modified_by`) was weighed and not taken.
- **No switch** for sites that want the agent to change any draft: no user story asks for it.
- **ERPNext enforces the rule too**, decided and done on 2026-11-02 after a trial on the end-to-end site: the draft DocTypes' write only if creator (REQ-001 Terms), in a second role of the agent user, since ERPNext's role permission manager edits one rule per role and DocType. Reads, lists with child rows and the warning comments still reach every draft; a person's draft can't be changed or discarded with the agent's key.
