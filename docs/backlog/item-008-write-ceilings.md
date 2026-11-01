# ITEM-008: Write ceilings from configuration

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | feature |
| **Origin** | [Analysis 001](../analysis/analysis-001-excessive-agency-review.md#35-write-operations), finding 5 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |

## Summary

Let a deployment cap what the agent may write: a highest grand total per draft, and a highest number of drafts created per hour. A manipulated agent then can't fill the review queue or slip an outsized amount among routine drafts.

## Context

The input limits are technical (1e9 per rate or amount, 10,000 per quantity, 20 rows), and nothing limits how many drafts an agent creates. The duplicate check catches retries, but the agent can pass `allow_duplicate: true` itself. Drafts wait for a person, but a reviewer facing a hundred drafts checks each less.

## Conditions

- Two optional variables, off when unset, for example `ENTERICH_MAX_DRAFT_TOTAL` (in the company's currency) and `ENTERICH_MAX_DRAFTS_PER_HOUR`; REQ-002's configuration and the configuration guide first.
- The total is checked on ERPNext's computed grand total: before the insert where Enterich can compute it, otherwise the draft isn't saved. Decide which; a saved draft over the ceiling must not stay behind silently.
- The hourly count comes from ERPNext (the agent user's documents of the draft DocTypes created in the last hour), not from Enterich's memory, so it holds across replicas and restarts.
- A refusal names the limit and says that the operator sets it; no limit depends on the client asking for approval.

## Open Questions

- A ceiling per DocType (journal entries carry other amounts than invoices), or one for all?
- Count `allow_duplicate` creates separately, with a lower limit?
- Updates too: an update can raise a draft's total as well as a create.
- The agent user's name: shared with [ITEM-005](item-005-updates-only-own-drafts.md).
