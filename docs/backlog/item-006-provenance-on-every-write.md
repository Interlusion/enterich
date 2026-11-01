# ITEM-006: Provenance on every write

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | improvement |
| **Origin** | [Analysis 001](../analysis/analysis-001-excessive-agency-review.md#33-provenance), finding 3 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |

## Summary

Mark every draft Enterich creates or changes in ERPNext with where it came from: an "Enterich:" comment naming the operation, the token's session (`sid`) and the time, and for an update the fields it changed. The reviewer and the auditor then see the origin in the draft's timeline, and can find the conversation's log lines from it.

## Context

Today a draft shows only the agent user as owner, and ERPNext's version history shows its changes. Session, operation and arguments are in Enterich's `operation` log line ([REQ-002-PRS-NF008](../specs/req-002-service.md#req-002-prs-nf008-log)), which lives on the platform's log store, apart from the books. A comment comes only with warnings ([REQ-001-PRS-F015](../specs/req-001-core.md#req-001-prs-f015-warnings-on-the-draft)). The auditor's expectation is "for every change, who made it and through which connection" ([REQ-001-P2](../specs/req-001-core.md#req-001-p2-the-auditor)).

## Conditions

- One comment per write, through the call Enterich already makes (`frappe.desk.form.utils.add_comment`); the warnings go into the same comment, so a draft gets no more comments than writes.
- Plain text, escaped as the warnings are; no arguments beyond the changed field names, no outside text, no token.
- A failed comment is reported in the result, as for warnings today; the draft stays.
- The `operation` log line also carries the JSON-RPC request ID, so a comment, a log line and a client's own record can be matched.
- REQ-001-PRS-F015 and REQ-002-PRS-NF008 change first, then tests, then code; the reviewing guide describes the comment.

## Open Questions

- Is `sid` the right handle in a comment that everyone with read on the draft sees, or a short hash of it that still matches the log?
- Does a task or conversation ID exist that clients pass on their own (MCP `_meta`), so the comment can name the task and not only the session? Enterich must not depend on it ([REQ-002-PRS-NF004](../specs/req-002-service.md#req-002-prs-nf004-no-client-specific-behaviour)).
