# ITEM-008: Write ceilings from configuration

| Meta | Value |
| :- | :- |
| **Status** | IMPLEMENTED |
| **Type** | feature |
| **Origin** | [Analysis 001](../../analysis/analysis-001-excessive-agency-review.md#35-write-operations), finding 5 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |
| **Implemented** | 2026-11-03, the limit of drafts per hour only ([REQ-001-PRS-F019](../../specs/req-001-core.md#req-001-prs-f019-drafts-per-hour)); comes with the release after v0.2.1 |

## Summary

Let a deployment cap what the agent may write: a highest grand total per draft, and a highest number of drafts created per hour. A manipulated agent then can't fill the review queue or slip an outsized amount among routine drafts.

## Context

The input limits are technical (1e9 per rate or amount, 10,000 per quantity, 20 rows), and nothing limits how many drafts an agent creates. The duplicate check catches retries, but the agent can pass `allow_duplicate: true` itself. Drafts wait for a person, but a reviewer facing a hundred drafts checks each less.

## Conditions

- Two optional variables, off when unset, for example `ENTERICH_MAX_DRAFT_TOTAL` (in the company's currency) and `ENTERICH_MAX_DRAFTS_PER_HOUR`; REQ-002's configuration and the configuration guide first.
- The total is checked on ERPNext's computed grand total: before the insert where Enterich can compute it, otherwise the draft isn't saved. Decide which; a saved draft over the ceiling must not stay behind silently.
- The hourly count comes from ERPNext (the agent user's documents of the draft DocTypes created in the last hour), not from Enterich's memory, so it holds across replicas and restarts. The agent user's name comes from `Erpnext.user()`, as for [ITEM-005](item-005-updates-only-own-drafts.md).
- A refusal names the limit and says that the operator sets it; no limit depends on the client asking for approval.

## Open Questions

None. Decided on 2026-11-03:

- **One limit, drafts per hour** (`ENTERICH_MAX_DRAFTS_PER_HOUR`); no ceiling on amounts for now. A ceiling on amounts would need one per DocType and a rule for a draft ERPNext saves over it, and the reviewer sees the amount anyway. A quick line in the [backlog](../backlog.md) keeps it to revisit.
- **Counted per DocType, with one number:** each create counts only its own DocType, so it needs no read right beyond its own, and two invoices don't hold back a journal entry.
- **What counts:** the documents the agent user created in the assigned company in the last 60 minutes, whatever their state now, read from ERPNext (`owner`, `creation`). `allow_duplicate` creates count like any other; updates don't count.
- **Order:** the count comes after the duplicate check, so a create repeated after a lost answer still learns of its first draft.
- **Its worth is small:** drafts wait for a person, and a limit caps how many, not what they say. A check of the drafts' content is [ITEM-010](../item-010-draft-validator.md).
