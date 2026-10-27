# REQ-005: Erpel Procure to Pay — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations of the buying side of the assigned company: suppliers, purchase invoices, purchase tax templates and open payables. The agent reads them and prepares drafts of purchase invoices, typically from an incoming supplier invoice, which a person reviews and submits.

Out of scope: purchase orders and receipts; stock (drafts never update stock); returns (debit notes) as drafts; payments, which belong to bank and cash (REQ-007).

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-005-P1-1. As the operator, I need the agent to tell me which supplier invoices are open and when they fall due, so that I pay on time.
- REQ-005-P3-1. As the bookkeeper, I need the agent to turn an incoming supplier invoice into a purchase invoice draft, and to notice when that invoice is already recorded, so that I only review and submit.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## URS — Functional

#### REQ-005-URS-F001: Read the buying side

**Description**: The agent SHALL be able to read suppliers with their addresses, purchase invoices with their rows, the purchase tax templates and the Accounts Payable report of the assigned company.

**Related User Stories**: REQ-005-P1-1, REQ-005-P3-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: Payables answer "what is due", and a draft needs exact supplier and template names.

#### REQ-005-URS-F002: Prepare purchase invoices

**Description**: The agent SHALL be able to create and change drafts of purchase invoices, and a supplier invoice already recorded SHALL NOT be recorded again unnoticed.

**Related User Stories**: REQ-005-P3-1 | **Refines**: REQ-001-URS-F002, REQ-001-URS-F007 | **Rationale**: The same supplier invoice arriving twice (by mail and by portal) is a common way to pay twice.

## PRS — Functional

#### REQ-005-PRS-F001: Supplier operations

**Description**: Erpel SHALL offer `list_suppliers` and `get_supplier` as the catalogue below defines them; `get_supplier` SHALL return the supplier's addresses.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- `get_supplier` returns the addresses linked to the supplier, and no other party's addresses.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-005-PRS-F002: Purchase invoice reads

**Description**: Erpel SHALL offer `list_purchase_invoices` and `get_purchase_invoice` as the catalogue below defines them, with the invoice states of REQ-001's Operation Conventions.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- `state` accepts exactly draft, unpaid, overdue, paid, return and cancelled; `overdue` uses today in the configured time zone.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-005-PRS-F003: Purchase tax templates

**Description**: Erpel SHALL offer `list_purchase_tax_templates` as the catalogue below defines it.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- Only purchase templates are returned, never sales templates.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-005-PRS-F004: Payables

**Description**: Erpel SHALL offer `report_accounts_payable` as the catalogue below defines it, with `total_outstanding` over all rows, not only the returned page.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- The report call carries exactly the fixed filters of the ERPNext calls table; `total_outstanding` equals the sum over all rows when `limit` returns fewer.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Erpel's test suite; the integration test against a real ERPNext v16 site (backlog).

#### REQ-005-PRS-F005: Purchase invoice drafts

**Description**: Erpel SHALL offer `create_draft_purchase_invoice` and `update_draft_purchase_invoice` as the catalogue below defines them; it SHALL send `set_posting_time` 1 whenever it sends a `posting_date`, and `update_stock` 0 on every create.

**Related URS**: REQ-005-URS-F002

**Definition of Done**:

- An update that sets `posting_date` on a draft created without one keeps it.
- Every create body carries `update_stock` 0.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-005-PRS-F006: Duplicate match for purchase invoices

**Description**: For REQ-001-PRS-F005, a purchase invoice create SHALL match:

- when `bill_no` is given, a draft or submitted purchase invoice of the assigned company with the same supplier and `bill_no`;
- otherwise, a draft with the same supplier, the same posting date (the given one, or today) and the same items (item codes and quantities, in any order).

**Related URS**: REQ-005-URS-F002, REQ-001-URS-F007

**Definition of Done**:

- A create with a supplier and `bill_no` already on a submitted invoice is refused naming it; a cancelled one doesn't count.
- Without `bill_no`, a create matching a draft is refused naming it; one that differs in a quantity, an item or the date goes through.
- Verification: test.
- Evidence: Erpel's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

### Reads

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_suppliers` | `search` (ID, supplier name), `include_disabled`, `limit`, `offset` | `name`, *`supplier_name`*, `supplier_type`, `supplier_group`, *`tax_id`*, `default_currency`, `disabled` |
| `get_supplier` | **`name`** | as above, plus `payment_terms`, `addresses` \[`name`, `address_type`, `is_primary_address`, *`address_line1`*, *`address_line2`*, *`city`*, *`pincode`*, `country`\] |
| `list_purchase_invoices` | `supplier`, `state` (draft, unpaid, overdue, paid, return, cancelled), `from_date`, `to_date` (posting date), `limit`, `offset` | `name`, `supplier`, *`supplier_name`*, *`bill_no`*, `bill_date`, `posting_date`, `due_date`, `currency`, `net_total`, `grand_total`, `outstanding_amount`, `status`, `docstatus`, `is_return`, `owner`, `modified` |
| `get_purchase_invoice` | **`name`** | as above, plus `taxes_and_charges`, `total_taxes_and_charges`, `return_against`, *`remarks`*, `items` \[`item_code`, *`item_name`*, *`description`*, `qty`, `uom`, `rate`, `amount`, `expense_account`, `item_tax_template`, `cost_center`\], `taxes` \[`charge_type`, `account_head`, `add_deduct_tax`, `rate`, `tax_amount`, `description`\], `url`, `truncated` |
| `list_purchase_tax_templates` | `include_disabled`, `limit`, `offset` | `name`, `title`, `is_default`, `tax_category`, `disabled` |
| `report_accounts_payable` | `as_of_date` (default today), `supplier`, `ageing_based_on` (due_date, posting_date; default due_date), `limit`, `offset` | rows \[`party`, `voucher_type`, `voucher_no`, `posting_date`, `due_date`, `invoiced`, `paid`, `credit_note`, `outstanding`, `currency`, `age`, `ageing` {`range0` (not yet due) to `range5`, as ERPNext's default ranges 30, 60, 90, 120 days}\]; `total_outstanding` over all rows |

Supplier names are not in report rows; `get_supplier` gives them.

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_purchase_invoice` | **`supplier`**; `bill_no`, `bill_date`; `posting_date` (default today), `due_date` (default from payment terms); **`items`** (1–20) \[**`item_code`**, **`qty`**, **`rate`**, `uom`, `expense_account`, `cost_center`\]; `taxes_and_charges`; `remarks`; `allow_duplicate` | the given fields; `set_posting_time` 1 when `posting_date` is given; `taxes` from the template; `update_stock` 0; `company`; `docstatus` 0 |
| `update_draft_purchase_invoice` | **`name`**, **`modified`**; at least one of `supplier`, `bill_no`, `bill_date`, `posting_date`, `due_date`, `items`, `taxes_and_charges`, `remarks` | the given fields; `set_posting_time` 1 when `posting_date` is given; `taxes` when `taxes_and_charges` is given (none when it is cleared); `modified` |

- Clearable on update: `remarks`, `bill_no`, `taxes_and_charges` (with its rows).
- Results add: `supplier`, `posting_date`, `due_date`, `currency`, `net_total`, `total_taxes_and_charges`, `grand_total`, `taxes` \[`account_head`, `rate`, `tax_amount`\], the row count.

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| suppliers | Supplier; Address through its Dynamic Link to the supplier | — | `name` |
| purchase invoices | Purchase Invoice | `company` | `posting_date` desc, `name` desc |
| `list_purchase_tax_templates` | Purchase Taxes and Charges Template | `company` | `name` |
| `report_accounts_payable` | Accounts Payable | `company`, `report_date`, `party_type` Supplier, `ageing_based_on` | ERPNext's |
| duplicate check with `bill_no` | Purchase Invoice | `company`, `docstatus` 0 or 1, `supplier`, `bill_no` | — |
| duplicate check without `bill_no` | Purchase Invoice | `company`, `docstatus` 0, `supplier`, `posting_date` | — |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_suppliers`, `get_supplier` | Supplier, Address: read |
| `list_purchase_invoices`, `get_purchase_invoice` | Purchase Invoice: read |
| `list_purchase_tax_templates` | Purchase Taxes and Charges Template: read |
| `report_accounts_payable` | Purchase Invoice, Payment Ledger Entry: read, report; the role added to the Accounts Payable report |
| `create_draft_purchase_invoice`, `update_draft_purchase_invoice` | Purchase Invoice: read, create, write; Supplier, Address, Item, Account, Cost Center, Purchase Taxes and Charges Template: read (ERPNext reads them while saving); Company, Currency, UOM, Price List, Payment Terms Template, Project: select |

Warnings are added to a draft as a comment, which needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- Suppliers, purchase invoices, purchase tax templates and payables are readable as catalogued, for the assigned company only.
- Purchase invoice drafts are created and updated with exactly the catalogued fields, never updating stock.
- A supplier invoice number already recorded for the supplier is refused as a possible duplicate unless the agent allows it.

## Assumptions

Checked against ERPNext v16.52 source:

- An invoice saved with `set_posting_time` 0 gets today as posting date.

Not checked yet:

- The rights in the Rights section are the minimum; the integration test proves them (REQ-002-PRS-NF013).
- ERPNext computes `due_date` from the supplier's payment terms when it isn't given.

## Open Questions

None at the moment.
