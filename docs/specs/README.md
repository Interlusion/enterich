# Requirement Specifications

REQ-001 holds the core: the personas, stories and terms, and what every operation shares. REQ-002 holds the service around the operations. Each further spec holds the operations of one accounting area. Every spec has user requirements (URS, what is needed), product requirements (PRS, what is built, each with a Definition of Done) and acceptance criteria, and always shows the current state.

| Spec | Area | Status |
| :- | :- | :- |
| [REQ-001](req-001-core.md) | Core: personas, stories and terms, and the rules every operation follows | Baselined |
| [REQ-002](req-002-service.md) | Service: access and token check, protocol, configuration, logging, limits, health | Baselined |
| [REQ-003](req-003-master-data.md) | Master data: items | Baselined |
| [REQ-004](req-004-order-to-cash.md) | Order to cash: customers, sales invoices, receivables | Baselined |
| [REQ-005](req-005-procure-to-pay.md) | Procure to pay: suppliers, purchase invoices, payables | Baselined |
| [REQ-006](req-006-record-to-report.md) | Record to report: accounts, cost centres, journal entries, ledger, trial balance | Baselined |
| [REQ-007](req-007-bank-and-cash.md) | Bank and cash: bank accounts, bank transactions, payments | Baselined |

Why the specs are cut this way: [ADR-007](../arc42/adr/ADR-007-specs-by-accounting-area.md).

## Reading and writing

- **For any operation, read REQ-001 and the operation's area spec.** [REQ-001's Requirement Rules](req-001-core.md#requirement-rules) say how the area specs relate to it.
- **For access, configuration, logging or limits, read REQ-002,** with REQ-001's terms.
- **An operation belongs to the area of its main DocType or report**: the one it lists, reads, creates or updates. Records it only touches on the way (the addresses in `get_customer`) don't count.
- **The map below decides.** For a DocType or report not yet in it: if one area uses it, that area; if several do, the area that maintains it, meaning the one in which people create and change those records; if no area maintains it, master data. Add the new entry to the map first.

| Area | Main DocTypes and reports |
| :- | :- |
| REQ-003 Master data | Item |
| REQ-004 Order to cash | Customer, Sales Invoice, Sales Taxes and Charges Template, Accounts Receivable |
| REQ-005 Procure to pay | Supplier, Purchase Invoice, Purchase Taxes and Charges Template, Accounts Payable |
| REQ-006 Record to report | Account, Cost Center, Journal Entry, General Ledger, Trial Balance |
| REQ-007 Bank and cash | Bank Account, Bank Transaction, Payment Entry |

## IDs

Requirement, user story and persona IDs always carry the spec's ID: `REQ-004-PRS-F005`, `REQ-001-P1-2`, `REQ-001-P1`, never a bare `PRS-F005`. This holds in the specs, the other docs, code comments, tests and commit messages.

The project code is **ERPL**. Outside this repository, IDs carry it: `ERPL-REQ-004-PRS-F005`, or `ERPL-REQ-004` for a whole spec. The code never changes, since other repositories cite it.

## Changes

A spec is Draft until the maintainer baselines it, and edited in place until then. After baseline, a substantive change (a requirement added, removed or changed) is folded into the body and a sibling `req-NNN-name.history.md` records the dated reason, most recent first. Until the first release, details found while building Enterich are folded into the body without a history entry.

Deployments keep their own requirements elsewhere and trace them to these IDs. A change a deployment needs arrives here as a change to these specs, never as a deployment fact.
