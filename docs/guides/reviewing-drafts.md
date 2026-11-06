# Reviewing the agent's drafts

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: matches what is built |

For the people who check and submit what the agent prepares (the bookkeeper of [REQ-001](../specs/req-001-core.md#personas)). Everything happens in ERPNext; Enterich adds nothing to its interface.

## Finding the agent's drafts

The agent works as its own ERPNext user, so its drafts carry that user as owner.

- In any list (Sales Invoice, Purchase Invoice, Journal Entry, Payment Entry), filter by **Status: Draft** and **Owner: the agent user**, and save the filter.
- The agent also gives a link to each draft it prepares, if you follow the conversation.

## Warnings

When something about a draft looks wrong, Enterich adds a comment to it, in the draft's timeline, starting with "Enterich:" ([REQ-001-PRS-F015](../specs/req-001-core.md#req-001-prs-f015-origin-and-warnings-on-the-draft)). For example:

- **Possible duplicate:** a matching document existed, and the agent created the draft anyway. The comment names the match.
- **A value ERPNext set differently:** a rate a pricing rule changed, an expense account ERPNext replaced, or journal totals that differ after ERPNext rounded each row. The comment names the row and both values.
- **A payment not fully allocated:** part of a payment isn't set against an invoice and stays an advance, or the bank account and the party's account are in two currencies, so the received amount and the exchange rates need correcting. The comment names the amount or both currencies.

Each area spec lists the warnings of its operations ([specs index](../specs/README.md)).

## Returns

The agent drafts credit notes and debit notes from ERPNext's own return of the invoice, as the invoice's **Return / Credit Note** (or **Return / Debit Note**) action does: they are sales or purchase invoices with **Is Return** set, in the same lists. ERPNext leaves **Update Outstanding for Self** ticked, so the return keeps its own outstanding amount, to be reconciled with the invoice or paid back; untick it before submitting if the invoice's outstanding amount should be lowered instead. On a debit note, check that **Supplier Invoice No** is the supplier's credit note number, not the invoice's.

The agent drafts no partial return of an invoice with a fixed discount or charge, such as freight: ERPNext's return would credit those amounts in full. Make such a return in ERPNext and adjust the discount and charges by hand. A credit note doesn't take back stock that a delivery note delivered; for that, make a return of the delivery note.

Read the timeline before submitting.

## Correcting a draft

Enterich lets the agent change only drafts it created. A draft you or a colleague started is refused to the agent, even though it can read it. A draft of the agent's that you corrected can still be changed by it, after it has read your version; read the version history before submitting.

Change the agent's draft as usual. If the agent later tries to change it again, it is refused because the draft changed since it was read, and it has to read your version first. Your correction is never overwritten unseen.

## What the agent can't do

Submit, cancel, amend, delete or discard. Only you do that.

## References

- [Specs index](../specs/README.md)
- [Configuration](configuration.md)
