# ITEM-007: Party IDs as outside text

| Meta | Value |
| :- | :- |
| **Status** | IMPLEMENTED |
| **Type** | improvement |
| **Origin** | [Analysis 001](../../analysis/analysis-001-excessive-agency-review.md#34-outside-data-in-results), finding 4 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |
| **Implemented** | 2026-11-03, as option C with A's recommendation |

## Summary

Close the gap in the outside-text marking that party IDs leave: by default ERPNext names a customer or supplier by its name, so the ID carries text the party chose, outside `outside_text`.

## Context

[REQ-001-PRS-NF001](../../specs/req-001-core.md#req-001-prs-nf001-outside-text-marked) puts `customer_name` and `supplier_name` under `outside_text`. ERPNext v16's defaults for Selling Settings "Customer Naming By" and Buying Settings "Supplier Naming By" are the party's name, so on such a site the same text also arrives as `name`, `customer`, `supplier` or `party`: in party lists and gets, invoices, the aged reports, the General Ledger, bank transactions and payment entries. Names are at most 140 characters, enough for an instruction.

## Options

- **A. Naming series required:** the configuration guide requires naming by naming series for Customer and Supplier; Enterich checks the two settings at start and warns, or refuses to start. IDs then carry no outside text; existing parties keep their names.
- **B. IDs marked where they may carry a name:** every field holding a party ID appears under `outside_text` as well, and the description says the ID is still the value to pass on. The result shape changes for each operation that returns a party.
- **C. Documented only:** the configuration guide and the tool note say that party IDs may carry outside text.

## Open Questions

None. Decided on 2026-11-03:

- **C, with A's recommendation:** the [configuration guide](../../guides/configuration.md#what-the-site-must-provide) recommends naming customers and suppliers by naming series for every site, and says that existing parties keep their names.
- **No check at start:** on a site where people create parties by hand, an odd name is likely to be noticed; the risk is real where parties come from a web shop, a portal or an import, and the guide's recommendation covers those. The check would also need read on Selling Settings and Buying Settings.
- **No marking of IDs (B):** it would change the shape of almost every result for a small risk.
- **Other IDs:** documents, payments and bank transactions are named by series; accounts, cost centres, tax templates, units and bank accounts are set up by the site's own staff. Items can carry a supplier's text where they are imported from a catalogue, and addresses are named after their title, usually the party's name, also with parties named by series; both are left as they are.
