# REQ-005: Enterich Procure to Pay — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations of the buying side of the assigned company: suppliers, purchase invoices, purchase tax templates and open payables. The agent reads them and prepares drafts of purchase invoices, typically from an incoming supplier invoice, and of returns (debit notes) against them, which a person reviews and submits.

Out of scope: purchase orders and receipts; stock (drafts never update stock); debit notes without returned items, such as a price reduction after the fact; returns not against an invoice, returns of invoices that updated stock, were paid on entry or are on hold, and returns of part of an invoice with a fixed discount or charge; payments, which belong to bank and cash (REQ-007).

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-005-P1-1. As the operator, I need the agent to tell me which supplier invoices are open and when they fall due, so that I pay on time.
- REQ-005-P3-1. As the bookkeeper, I need the agent to turn an incoming supplier invoice into a purchase invoice draft, and to notice when that invoice is already recorded, so that I only review and submit.
- REQ-005-P3-2. As the bookkeeper, I need the agent to turn a supplier's credit note for returned items into a debit note against the purchase invoice they were billed on, so that I only review and submit.

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

#### REQ-005-URS-F003: Prepare debit notes

**Description**: The agent SHALL be able to create and change drafts of returns (debit notes) against submitted purchase invoices of the assigned company, for all or some of their items.

**Related User Stories**: REQ-005-P3-2 | **Refines**: REQ-001-URS-F002 | **Rationale**: A debit note must match the invoice's rates and taxes; taking them from the invoice is the work the agent saves.

## PRS — Functional

#### REQ-005-PRS-F001: Supplier operations

**Description**: Enterich SHALL offer `list_suppliers` and `get_supplier` as the catalogue below defines them; `get_supplier` SHALL return the supplier's addresses.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- `get_supplier` returns the addresses linked to the supplier, and no other party's addresses.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F002: Purchase invoice reads

**Description**: Enterich SHALL offer `list_purchase_invoices` and `get_purchase_invoice` as the catalogue below defines them, with the invoice states of REQ-001's Operation Conventions.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- `state` accepts exactly draft, unpaid, overdue, paid, return and cancelled; `overdue` uses today in the configured time zone.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F003: Purchase tax templates

**Description**: Enterich SHALL offer `list_purchase_tax_templates` as the catalogue below defines it.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- Only purchase templates are returned, never sales templates.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F004: Payables

**Description**: Enterich SHALL offer `report_accounts_payable` as the catalogue below defines it, with `total_outstanding` over all rows, not only the returned page.

**Related URS**: REQ-005-URS-F001

**Definition of Done**:

- The report call carries exactly the fixed filters of the ERPNext calls table; `total_outstanding` equals the sum over all rows when `limit` returns fewer.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-005-PRS-F005: Purchase invoice drafts

**Description**: Enterich SHALL offer `create_draft_purchase_invoice` and `update_draft_purchase_invoice` as the catalogue below defines them; it SHALL send `set_posting_time` 1 whenever it sends a `posting_date`, and `update_stock` 0 on every create.

**Related URS**: REQ-005-URS-F002

**Definition of Done**:

- An update that sets `posting_date` on a draft created without one keeps it.
- Every create body carries `update_stock` 0.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F006: Duplicate match for purchase invoices

**Description**: For REQ-001-PRS-F005, a purchase invoice create SHALL match:

- when `bill_no` is given, a draft or submitted purchase invoice of the assigned company with the same supplier and `bill_no`;
- otherwise, a draft with the same supplier, the same posting date (the given one, or today) and the same items (item codes and quantities, in any order, leaving out free-item rows a pricing rule added).

An update that gives a `bill_no` SHOULD carry a warning, added to the draft, when another draft or submitted purchase invoice of the assigned company has the same supplier and `bill_no`.

**Related URS**: REQ-005-URS-F002, REQ-001-URS-F007

**Definition of Done**:

- A create with a supplier and `bill_no` already on a submitted invoice is refused naming it; a cancelled one doesn't count.
- Without `bill_no`, a create matching a draft is refused naming it; one that differs in a quantity, an item or the date goes through.
- An update giving a `bill_no` already on a submitted invoice of the supplier warns naming it; the draft's own `bill_no` doesn't count.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F007: Expense accounts ERPNext set

**Description**: A purchase invoice create or update result SHOULD carry a warning for each item row whose given `expense_account` ERPNext saved as another (for a stock item under perpetual inventory, Stock Received But Not Billed). Accounts are compared without regard to case, as ERPNext saves a link in the case of the stored name. Rows are matched as REQ-001-PRS-F016 matches them, and count towards its 20 named rows.

**Related URS**: REQ-005-URS-F002, REQ-001-URS-F009

**Definition of Done**:

- A row given an expense account that ERPNext replaces returns a warning naming the row, the item and both accounts, and the warning is added to the draft.
- A row without an expense account, and one whose account ERPNext keeps, also in another case, return no warning.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-005-PRS-F008: Purchase return drafts

**Description**: Enterich SHALL offer `create_draft_purchase_return` and `update_draft_purchase_return` as the catalogue below defines them, building the draft's rows from ERPNext's return of the invoice. Before saving, it SHALL refuse a return against an invoice that isn't a submitted purchase invoice of the assigned company, is itself a return, updated stock, was paid on entry or is on hold; an item that isn't on the invoice; a quantity above what is left to return of an item; an invoice with nothing left to return; and, for an invoice with a fixed discount or charge, any return but one of the whole invoice with nothing returned before. An update giving `items` or `posting_date` SHALL refuse the invoices a create refuses, and an update of a return draft without `return_against` SHALL be refused. A return dated the invoice's posting date SHALL carry the invoice's posting time. Each row SHALL be sent with its received quantity equal to its quantity and no rejected quantity. `update_draft_purchase_invoice` SHALL refuse a return draft, naming `update_draft_purchase_return`, and `update_draft_purchase_return` a draft that isn't a return, naming `update_draft_purchase_invoice`; both without a write.

**Related URS**: REQ-005-URS-F003

**Definition of Done**:

- A create without `items` sends every row ERPNext's return holds, at the quantity left to return, negative; one with `items` sends only the rows of the given items.
- An item on two rows of the invoice, with 3 and 2 left to return, returned at 4, is sent as two rows at −3 and −1, each linked to its invoice row.
- An item invoiced at 2 and returned at 1 is sent with `qty`, `received_qty` and `stock_qty` −1 and `rejected_qty` 0.
- An item invoiced at 0.3 with 0.1 returned is returned at 0.2.
- Against an invoice with a fixed discount, or with a tax row of charge type Actual, a return of every item goes through; one of some items, and one after a submitted return against it, are refused, without a write.
- A return dated the invoice's posting date is sent with the invoice's posting time; one dated later without a posting time.
- A return against a draft, a cancelled, a return, a stock-updating, a paid-on-entry or an on-hold purchase invoice, or against one that doesn't exist for the assigned company, is refused naming `return_against`, without a write; an item not on the invoice, or one returned above what is left, is refused naming `items`, the item and the quantity left.
- A create with `bill_no` sends it instead of the invoice's; one without keeps the invoice's, as ERPNext's return copies it.
- An update giving `items` replaces the draft's rows with those of ERPNext's return of the draft's invoice; one giving only `posting_date`, `bill_no`, `bill_date` or `remarks` sends no rows; an empty `bill_no` clears it.
- An update giving `items` or `posting_date` of a return whose invoice was cancelled since, or whose `return_against` a person changed to an invoice of another company, is refused naming `return_against`; an update of a return whose `return_against` a person cleared is refused naming `name`; all without a write.
- Verification: test.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-005-PRS-F009: Duplicate match for purchase returns

**Description**: For REQ-001-PRS-F005, a purchase return create SHALL match a draft return of the assigned company against the same invoice, and, when `bill_no` is given, a draft or submitted purchase invoice of the assigned company with the same supplier and `bill_no`, returns included. An update that gives a `bill_no` SHOULD carry a warning, added to the draft, when another draft or submitted purchase invoice of the assigned company has the same supplier and `bill_no`.

**Related URS**: REQ-005-URS-F003, REQ-001-URS-F007

**Definition of Done**:

- A create against an invoice with a draft return is refused naming it; a submitted or cancelled return against it doesn't count.
- A create with a `bill_no` already on a draft or submitted purchase invoice of the supplier is refused naming it; with `allow_duplicate`, it goes through with a warning naming it. An update giving such a `bill_no` warns naming it; the draft's own `bill_no` doesn't count.
- Verification: test.
- Evidence: Enterich's test suite.

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
| `report_accounts_payable` | `as_of_date` (default today), `supplier`, `ageing_based_on` (due_date, posting_date; default due_date), `limit`, `offset` | rows \[`party`, `voucher_type`, `voucher_no`, *`bill_no`*, `bill_date`, `posting_date`, `due_date`, `invoiced`, `paid`, `credit_note`, `outstanding`, `currency`, `age`, `ageing` {`range0` (not yet due) to `range5`, as ERPNext's default ranges 30, 60, 90, 120 days}\]; `total_outstanding` over all rows |

Supplier names are not in report rows; `get_supplier` gives them. `bill_no` and `bill_date` are the supplier's invoice number and date, as ERPNext's report shows them; debit notes are under `credit_note`, ERPNext's field name for both sides.

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_purchase_invoice` | **`supplier`**; `bill_no`, `bill_date`; `posting_date` (default today), `due_date` (default from payment terms, counted from `bill_date` when given); **`items`** (1–20) \[**`item_code`**, **`qty`**, **`rate`**, `uom`, `expense_account`, `cost_center`\]; `taxes_and_charges`; `remarks`; `allow_duplicate` | the given fields; `set_posting_time` 1 when `posting_date` is given; `payment_terms_template` "" when `due_date` is given (REQ-001-PRS-F017); `taxes` from the template; `update_stock` 0; `apply_tds` 1 when the supplier has a tax withholding category or group, as the form sets it for a new invoice; `company`; `docstatus` 0 |
| `update_draft_purchase_invoice` | **`name`**, **`modified`**; at least one of `bill_no`, `bill_date`, `posting_date`, `due_date`, `items`, `taxes_and_charges`, `remarks` | the given fields; `set_posting_time` 1 when `posting_date` is given; `payment_terms_template`, `payment_schedule` and `due_date` as REQ-001-PRS-F017 says; `taxes` when `taxes_and_charges` is given (none when it is cleared); `modified` |

- `bill_no` is the supplier's invoice number as printed: a string of 1–140 characters without leading or trailing whitespace, not a name. Clearable on update: `remarks`, `bill_no`, `taxes_and_charges` (with its rows).
- The supplier isn't changed by an update: ERPNext would keep the first supplier's address, payment terms, price list and payable account. A draft for another supplier is a new draft.
- Rates come from the supplier's bill, so `rate` is required. Enterich never sends `ignore_pricing_rule`; REQ-001-PRS-F016 warns where a buying pricing rule replaced a given rate.
- Results add: `supplier`, `posting_date`, `due_date`, `currency`, `net_total`, `total_taxes_and_charges`, `grand_total`, `taxes` \[`account_head`, `rate`, `tax_amount`\], `items` \[`item_code`, `qty`, `rate`, `amount`, `expense_account`, `is_free_item`\].

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_purchase_return` | **`return_against`**; `items` (1–20) \[**`item_code`**, **`qty`**\]; `bill_no`, `bill_date`; `posting_date` (default today, sent either way); `remarks`; `allow_duplicate` | ERPNext's return of `return_against` (`make_debit_note`), without `name`, `owner` and the fields starting with `__`, in its rows too; with `items`, only the rows of the given items, at the given quantities; in each row `received_qty` equal to `qty` and `rejected_qty` 0; `bill_no`, `bill_date` and `remarks` when given; `posting_date`, `set_posting_time` 1, and the invoice's `posting_time` when `posting_date` is the invoice's; `company`; `docstatus` 0 |
| `update_draft_purchase_return` | **`name`**, **`modified`**; at least one of `items`, `bill_no`, `bill_date`, `posting_date`, `remarks` | `items` as for create, from ERPNext's return of the draft's `return_against`; `bill_no`, `bill_date`, `remarks`; `posting_date` with `set_posting_time` 1, and `posting_time` as for create; `modified` |

- `qty` is the quantity returned, as a positive number; Enterich sends it negative, as a return holds it. An item on several rows of the invoice is taken from them in row order, its paid rows before its free-item rows, each up to what is left to return on it. What is left is the invoice's quantity less the submitted returns against it, rounded to 9 decimal places; draft returns don't count.
- A fixed discount or charge is as REQ-004's catalogue says; Enterich drafts only a return of the whole invoice for an invoice with one.
- `bill_no` and `bill_date` are the number and date of the supplier's credit note, as for a purchase invoice. ERPNext's return copies the invoice's `bill_no`, which then names the invoice, not the credit note; give the credit note's.
- The supplier, the rates, the accounts and the taxes come from the invoice. An update doesn't change `return_against`: a return against another invoice is a new draft. Clearable on update: `remarks`, `bill_no`.
- ERPNext keeps a debit note's outstanding amount on the debit note itself (`update_outstanding_for_self`), to be set against the invoice or refunded; a person can untick it before submitting, so that the invoice's outstanding amount is lowered instead.
- A return is a purchase invoice: it counts towards the limit of drafts per hour with the purchase invoices, and lists show it among them with `is_return` true.
- Results add what a purchase invoice draft's do, and *`bill_no`*, `bill_date` and `return_against`.

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| suppliers | Supplier; Address through its Dynamic Link to the supplier | — | `name` |
| purchase invoices | Purchase Invoice | `company` | `posting_date` desc, `name` desc |
| `list_purchase_tax_templates` | Purchase Taxes and Charges Template | `company` | `name` |
| `report_accounts_payable` | Accounts Payable | `company`, `report_date`, `party_type` Supplier, `party` (a list holding `supplier`, when given), `ageing_based_on` (`Due Date` or `Posting Date`), `age_as_on` `Report Date`, `range` `30, 60, 90, 120` | ERPNext's |
| duplicate check with `bill_no`, also of a purchase return | Purchase Invoice | `company`, `docstatus` 0 or 1, `supplier`, `bill_no`; on update also `name` other than the draft | — |
| withholding on create | Supplier, its `tax_withholding_category` and `tax_withholding_group` | — | — |
| duplicate check without `bill_no` | Purchase Invoice, with `name`, `items.item_code`, `items.qty` and `items.is_free_item` (one row per item) in one call | `company`, `docstatus` 0, `supplier`, `posting_date` | — |
| purchase returns | the invoice with `frappe.client.get`; its return with `erpnext.accounts.doctype.purchase_invoice.purchase_invoice.make_debit_note` (`source_name`) | — | — |
| duplicate check of a purchase return | Purchase Invoice | `company`, `docstatus` 0, `is_return` 1, `return_against` | `name` |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_suppliers`, `get_supplier` | Supplier, Address: read |
| `list_purchase_invoices`, `get_purchase_invoice` | Purchase Invoice: read |
| `list_purchase_tax_templates` | Purchase Taxes and Charges Template: read |
| `report_accounts_payable` | Purchase Invoice: read, report; Journal Entry: read (the report lists them for due dates; with select only, they arrive without); the role added to the Accounts Payable report |
| `create_draft_purchase_invoice`, `update_draft_purchase_invoice` | Purchase Invoice: read, create, write only if creator; Supplier, Address, Item, Purchase Taxes and Charges Template: read (ERPNext or Enterich reads them while saving); Account: select (ERPNext lists the accounts) |
| `create_draft_purchase_return`, `update_draft_purchase_return` | Purchase Invoice: read, create, write only if creator; Supplier, Address, Item: read (ERPNext reads them while saving); Account: select (ERPNext lists the accounts) |

The DocTypes a draft only links to, such as its company, currency, units, price list, payment terms, project or cost centres, need no right: ERPNext checks a link without the user's permissions.

A return update giving `items` needs create on Purchase Invoice too: ERPNext maps the return of the invoice as a new document (`get_mapped_doc`).

Warnings are added to a draft as a comment, which needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- Suppliers, purchase invoices, purchase tax templates and payables are readable as catalogued, for the assigned company only.
- Purchase invoice drafts are created and updated with exactly the catalogued fields, never updating stock.
- Debit notes are drafted from the invoice's own return, for all or some of its items, never above what is left to return, and never crediting a fixed discount or charge in full for part of an invoice.
- A supplier invoice number already recorded for the supplier is refused as a possible duplicate unless the agent allows it.

## Assumptions

Checked against ERPNext v16.52 source:

- An invoice saved with `set_posting_time` 0 gets today, in the site's time zone (System Settings), as posting date at every save.
- A given rate is kept unless a price pricing rule for buying matches the row; then the rule sets the rate anew at every save and its name goes into the row's `pricing_rules`. Product pricing rules append free-item rows (`is_free_item`).
- The supplier's address, contact, payment terms, price list and accounts are filled in on save only where the draft has none; a supplier address of another supplier is refused.
- Without a due date, ERPNext counts one from `bill_date` when given, else from the posting date, by the supplier's payment terms template, else its supplier group's, else the company's; it never sets one before the posting date. A due date before `bill_date` is refused, and so is one later than the payment terms counted from `bill_date` allow; for a bill older than its terms, the due date ERPNext counts itself (never before the posting date) is such a date, so the agent gives the due date from the bill (`validate_due_date_with_template`).
- Under perpetual inventory, a stock item's `expense_account` is replaced on save by the company's Stock Received But Not Billed account unless the invoice updates stock (`set_expense_account`); the desk only shows a message.
- Buying Settings can require a purchase order for every row (`po_required`), or a purchase receipt for every row with a stock or asset item (`pr_required`, for invoices that don't update stock); ERPNext then refuses drafts without one, unless the supplier is allowed them (configuration guide).
- ERPNext refuses a `bill_no` already on a draft or submitted invoice of the same supplier in the same fiscal year only when Accounts Settings say so (`check_supplier_invoice_uniqueness`, off by default); Enterich's duplicate check therefore stays, over every year. Where the setting is on, ERPNext refuses even with `allow_duplicate`. Both compare `bill_no` in the database, so case follows its collation.
- ERPNext computes tax withholding only for an invoice with `apply_tds` set. A REST save leaves it at 0, and the form sets it only for a new invoice or a changed supplier, from the supplier's tax withholding category or group (`purchase_invoice.js`, `TaxWithholdingController`); Enterich therefore sends it on create. The withholding rows are among the result's `taxes`.
- Accounts Payable runs Accounts Receivable's code with the account type Payable: the same filters and columns, plus `bill_no` and `bill_date`, and debit notes in the `credit_note` column. Its rows are read through permission-checked lists of Purchase Invoice and Journal Entry.
- `make_debit_note` maps a submitted purchase invoice to an unsaved return as `make_sales_return` does a sales invoice (REQ-004's Assumptions), linking each row to its invoice row (`purchase_invoice_item`); it also copies the invoice's `bill_no`, its posting date, and its `on_hold` and `release_date`, which ERPNext refuses on save once the release date has passed. Each row's `received_qty` and `rejected_qty` are what is left of the invoice row's, whatever quantity is returned. The check for unique supplier invoice numbers doesn't run for a return.

Checked on a real ERPNext v16 site by hand (2026-11-03):

- `make_debit_note` for a submitted purchase invoice returned its row at −1, linked to the invoice row, with the invoice's `bill_no`, its posting date and no `bill_date`.

Checked on a real ERPNext v16 site by the end-to-end test:

- The rights in the Rights section suffice, and each is needed (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
