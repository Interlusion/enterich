# ITEM-007: Party IDs as outside text

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | improvement |
| **Origin** | [Analysis 001](../analysis/analysis-001-excessive-agency-review.md#34-outside-data-in-results), finding 4 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |

## Summary

Close the gap in the outside-text marking that party IDs leave: by default ERPNext names a customer or supplier by its name, so the ID carries text the party chose, outside `outside_text`.

## Context

[REQ-001-PRS-NF001](../specs/req-001-core.md#req-001-prs-nf001-outside-text-marked) puts `customer_name` and `supplier_name` under `outside_text`. ERPNext v16's defaults for Selling Settings "Customer Naming By" and Buying Settings "Supplier Naming By" are the party's name, so on such a site the same text also arrives as `name`, `customer`, `supplier` or `party`: in party lists and gets, invoices, the aged reports, the General Ledger, bank transactions and payment entries. Names are at most 140 characters, enough for an instruction.

## Options

- **A. Naming series required:** the configuration guide requires naming by naming series for Customer and Supplier; Enterich checks the two settings at start and warns, or refuses to start. IDs then carry no outside text; existing parties keep their names.
- **B. IDs marked where they may carry a name:** every field holding a party ID appears under `outside_text` as well, and the description says the ID is still the value to pass on. The result shape changes for each operation that returns a party.
- **C. Documented only:** the configuration guide and the tool note say that party IDs may carry outside text.

## Open Questions

- Which option, or A with C for existing parties?
- For A: which right the check at start needs (read on Selling Settings and Buying Settings), and whether that is acceptable next to the rule against write on any Settings DocType.
- Are other IDs set from outside text on common sites (items named by an imported supplier description, addresses named after the party)?
