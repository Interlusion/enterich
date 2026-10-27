# Reviewing the agent's drafts

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: describes the planned behaviour; nothing is built yet |

For the people who check and submit what the agent prepares (the bookkeeper of [REQ-001](../specs/req-001-core.md#personas)). Everything happens in ERPNext; Erpel adds nothing to its interface.

## Finding the agent's drafts

The agent works as its own ERPNext user, so its drafts carry that user as owner.

- In any list (Sales Invoice, Purchase Invoice, Journal Entry), filter by **Status: Draft** and **Owner: the agent user**, and save the filter.
- The agent also gives a link to each draft it prepares, if you follow the conversation.

## Warnings

When something about a draft looks wrong, Erpel adds a comment to it, in the draft's timeline, starting with "Erpel:". Two cases today:

- **Possible duplicate:** a matching document existed, and the agent created the draft anyway. The comment names the match.
- **Tax template without tax:** a tax template was given, but the draft's tax is zero.

Read the timeline before submitting.

## Correcting a draft

Change the draft as usual. If the agent later tries to change it again, it is refused because the draft changed since it was read, and it has to read your version first. Your correction is never overwritten unseen.

## What the agent can't do

Submit, cancel, amend, delete or discard. Only you do that.

## References

- [Specs index](../specs/README.md)
- [Configuration](configuration.md)
