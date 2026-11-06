# ITEM-010: A validator for the agent's drafts

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | idea |
| **Origin** | Discussion of [ITEM-008](archive/item-008-write-ceilings.md)'s worth, 2026-11-03 |
| **Created** | 2026-11-03 |
| **Author** | loxy (drafted with Claude) |

## Summary

A second, independent check of each draft the agent creates or changes, before a person submits it: another agent, or rules learned from the bookkeeper's corrections, that compares the draft with the books and flags what looks wrong. Limits cap how much the agent can do; a validator looks at what it did.

## Context / Motivation

Enterich's limits are about volume and reach: drafts only, the assigned company, the agent's own drafts, a limit of drafts per hour. What a draft says (the account, the amount, the party, the tax template) is checked only by the person who reviews it, and by Enterich's few warnings (possible duplicate, rate 0, tax template without tax). A reviewer who sees many good drafts checks each less, and an agent misled by outside text produces drafts that look routine.

Limiting the agent further would leave it unable to do its work. A check of its output keeps the agent capable and makes the review better.

## Options

- **A. A reviewer agent:** a second agent, ideally with another model, on its own Enterich instance with read operations only (`ENTERICH_TOOLS`) and its own agent user. It reads each new agent draft with the books around it (the party's earlier invoices, the usual accounts) and reports what it finds. Enterich needs no change, unless the findings go on the draft (a fixed comment operation).
- **B. Learned policies:** compare the agent's drafts with what people submitted from them (ERPNext's version history): which fields people corrected, for which party or item. Rules follow from that ("supplier X always books to account Y"), and new drafts are checked against them, as warnings.
- **C. ERPNext's workflow:** a workflow state such as "Checked" between draft and submit, which only the validator's role or a person may set; drafts the validator flagged stay unchecked. It makes the check visible in ERPNext, whichever of A or B does it.

## Open Questions

- Where it runs: inside Enterich (as warnings at create, like REQ-001-PRS-F015), beside it as its own service, or as a scheduled agent?
- What it may do: comment only, or also hold a draft (a workflow state)? It never submits.
- What it sees: the draft and the books only, or also the source the agent worked from (an incoming invoice, a bank line), which Enterich doesn't have?
- How findings reach the reviewer: a comment on the draft like Enterich's warnings (the comment of [ITEM-006](archive/item-006-provenance-on-every-write.md) could carry them), or a list of its own?
- How to tell it works: [ITEM-009](item-009-agent-eval-suite.md)'s cases, with drafts that are wrong on purpose, and its false alarms per week.
- Cost: one model call or more per draft.
