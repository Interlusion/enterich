# REQ-004: Enterich Order to Cash — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations of the selling side of the assigned company: customers, sales invoices, sales tax templates and open receivables. The agent reads them and prepares drafts of sales invoices, and of returns (credit notes) against them, which a person reviews and submits.

Out of scope: quotations, sales orders and delivery notes; credit notes without returned items, such as a price reduction after the fact; returns not against an invoice, returns that update stock, returns of POS invoices, and returns of part of an invoice with a fixed discount or charge; payments, which belong to bank and cash (REQ-007).

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-004-P1-1. As the operator, I need the agent to tell me which customers owe what and since when, so that I can follow up without searching lists.
- REQ-004-P3-1. As the bookkeeper, I need the agent to prepare sales invoice drafts with the right customer, items and taxes, so that I only review and submit.
- REQ-004-P3-2. As the bookkeeper, I need the agent to prepare a credit note for items a customer returned, against the invoice they were billed on, so that I only review and submit.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## URS — Functional

#### REQ-004-URS-F001: Read the selling side

**Description**: The agent SHALL be able to read customers with their addresses, sales invoices with their rows, the sales tax templates and the Accounts Receivable report of the assigned company.

**Related User Stories**: REQ-004-P1-1, REQ-004-P3-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: Receivables answer "who owes what", and a draft needs exact customer and template names.

#### REQ-004-URS-F002: Prepare sales invoices

**Description**: The agent SHALL be able to create and change drafts of sales invoices.

**Related User Stories**: REQ-004-P3-1 | **Refines**: REQ-001-URS-F002 | **Rationale**: Typing invoices is the work the agent saves.

#### REQ-004-URS-F003: Prepare credit notes

**Description**: The agent SHALL be able to create and change drafts of returns (credit notes) against submitted sales invoices of the assigned company, for all or some of their items.

**Related User Stories**: REQ-004-P3-2 | **Refines**: REQ-001-URS-F002 | **Rationale**: A credit note must match the invoice's rates and taxes; taking them from the invoice is the work the agent saves.

## PRS — Functional

#### REQ-004-PRS-F001: Customer operations

**Description**: Enterich SHALL offer `list_customers` and `get_customer` as the catalogue below defines them; `get_customer` SHALL return the customer's addresses.

**Related URS**: REQ-004-URS-F001

**Definition of Done**:

- `get_customer` returns the addresses linked to the customer, and no other party's addresses.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-004-PRS-F002: Sales invoice reads

**Description**: Enterich SHALL offer `list_sales_invoices` and `get_sales_invoice` as the catalogue below defines them, with the invoice states of REQ-001's Operation Conventions.

**Related URS**: REQ-004-URS-F001

**Definition of Done**:

- `state` accepts exactly draft, unpaid, overdue, paid, return and cancelled; `overdue` uses today in the configured time zone.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-004-PRS-F003: Sales tax templates

**Description**: Enterich SHALL offer `list_sales_tax_templates` as the catalogue below defines it.

**Related URS**: REQ-004-URS-F001

**Definition of Done**:

- Only sales templates are returned, never purchase templates.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-004-PRS-F004: Receivables

**Description**: Enterich SHALL offer `report_accounts_receivable` as the catalogue below defines it, with `total_outstanding` over all rows, not only the returned page.

**Related URS**: REQ-004-URS-F001

**Definition of Done**:

- The report call carries exactly the fixed filters of the ERPNext calls table; `total_outstanding` equals the sum over all rows when `limit` returns fewer.
- An `as_of_date` in the past ages the rows from that date, not from today; ERPNext's total row is not among the rows.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-004-PRS-F005: Sales invoice drafts

**Description**: Enterich SHALL offer `create_draft_sales_invoice` and `update_draft_sales_invoice` as the catalogue below defines them; it SHALL send `set_posting_time` 1 whenever it sends a `posting_date`, and SHALL send no `rate` for a row given without one, so that ERPNext prices it.

**Related URS**: REQ-004-URS-F002

**Definition of Done**:

- An update that sets `posting_date` on a draft created without one keeps it.
- A row given without `rate` is sent without one, and the result shows the rate ERPNext set.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-004-PRS-F006: Duplicate match for sales invoices

**Description**: For REQ-001-PRS-F005, a sales invoice create SHALL match a draft of the assigned company with the same customer, the same posting date (the given one, or today) and the same items (item codes and quantities, in any order, leaving out free-item rows a pricing rule added).

**Related URS**: REQ-004-URS-F002, REQ-001-URS-F007

**Definition of Done**:

- A create matching an existing draft is refused naming it; one that differs in a quantity, an item or the date goes through.
- A create matches a draft that has an added free-item row as well.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-004-PRS-F007: Sales return drafts

**Description**: Enterich SHALL offer `create_draft_sales_return` and `update_draft_sales_return` as the catalogue below defines them, building the draft's rows from ERPNext's return of the invoice. Before saving, it SHALL refuse a return against an invoice that isn't a submitted sales invoice of the assigned company, is itself a return, is a POS invoice or updated stock; an item that isn't on the invoice; a quantity above what is left to return of an item; an invoice with nothing left to return; and, for an invoice with a fixed discount or charge, any return but one of the whole invoice with nothing returned before. An update giving `items` or `posting_date` SHALL refuse the invoices a create refuses, and an update of a return draft without `return_against` SHALL be refused. A return dated the invoice's posting date SHALL carry the invoice's posting time. `update_draft_sales_invoice` SHALL refuse a return draft, naming `update_draft_sales_return`, and `update_draft_sales_return` a draft that isn't a return, naming `update_draft_sales_invoice`; both without a write.

**Related URS**: REQ-004-URS-F003

**Definition of Done**:

- A create without `items` sends every row ERPNext's return holds, at the quantity left to return, negative; one with `items` sends only the rows of the given items.
- An item on two rows of the invoice, with 3 and 2 left to return, returned at 4, is sent as two rows at −3 and −1, each linked to its invoice row.
- An item on a free-item row (`is_free_item`) before its paid row, returned at 1, is taken from the paid row.
- An item invoiced at 0.3 with 0.1 returned is returned at 0.2.
- Against an invoice with a fixed discount, or with a tax row of charge type Actual, a return of every item goes through; one of some items, and one after a submitted return against it, are refused, without a write.
- A return dated the invoice's posting date is sent with the invoice's posting time; one dated later without a posting time.
- A return against a draft, a cancelled, a return, a POS or a stock-updating sales invoice, or against one that doesn't exist for the assigned company, is refused naming `return_against`, without a write; an item not on the invoice, or one returned above what is left, is refused naming `items`, the item and the quantity left.
- An update giving `items` replaces the draft's rows with those of ERPNext's return of the draft's invoice; one giving only `posting_date` or `remarks` sends no rows.
- An update giving `items` or `posting_date` of a return whose invoice was cancelled since, or whose `return_against` a person changed to an invoice of another company, is refused naming `return_against`; an update of a return whose `return_against` a person cleared is refused naming `name`; all without a write.
- Verification: test.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-004-PRS-F008: Duplicate match for sales returns

**Description**: For REQ-001-PRS-F005, a sales return create SHALL match a draft return of the assigned company against the same invoice.

**Related URS**: REQ-004-URS-F003, REQ-001-URS-F007

**Definition of Done**:

- A create against an invoice with a draft return is refused naming it; a submitted or cancelled return against it doesn't count.
- Verification: test.
- Evidence: Enterich's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

### Reads

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_customers` | `search` (ID, customer name), `include_disabled`, `limit`, `offset` | `name`, *`customer_name`*, `customer_type`, `customer_group`, *`tax_id`*, `default_currency`, `disabled` |
| `get_customer` | **`name`** | as above, plus `payment_terms`, `addresses` \[`name`, `address_type`, `is_primary_address`, *`address_line1`*, *`address_line2`*, *`city`*, *`pincode`*, `country`\] |
| `list_sales_invoices` | `customer`, `state` (draft, unpaid, overdue, paid, return, cancelled), `from_date`, `to_date` (posting date), `limit`, `offset` | `name`, `customer`, *`customer_name`*, `posting_date`, `due_date`, `currency`, `net_total`, `grand_total`, `outstanding_amount`, `status`, `docstatus`, `is_return`, `owner`, `modified` |
| `get_sales_invoice` | **`name`** | as above, plus `taxes_and_charges`, `total_taxes_and_charges`, `return_against`, *`remarks`*, `items` \[`item_code`, *`item_name`*, *`description`*, `qty`, `uom`, `rate`, `amount`, `income_account`, `item_tax_template`, `cost_center`\], `taxes` \[`charge_type`, `account_head`, `rate`, `tax_amount`, `description`\], `url`, `truncated` |
| `list_sales_tax_templates` | `include_disabled`, `limit`, `offset` | `name`, `title`, `is_default`, `tax_category`, `disabled` |
| `report_accounts_receivable` | `as_of_date` (default today), `customer`, `ageing_based_on` (due_date, posting_date; default due_date), `limit`, `offset` | rows \[`party`, `voucher_type`, `voucher_no`, `posting_date`, `due_date`, `invoiced`, `paid`, `credit_note`, `outstanding`, `currency`, `age`, `ageing` {`range0` (not yet due) to `range5`, as ERPNext's default ranges 30, 60, 90, 120 days}\]; `total_outstanding` over all rows |

Customer names are not in report rows; `get_customer` gives them.

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_sales_invoice` | **`customer`**; `posting_date` (default today), `due_date` (default from payment terms); **`items`** (1–20) \[**`item_code`**, **`qty`**, `rate`, `uom`, `income_account`, `cost_center`\]; `taxes_and_charges`; `remarks`; `allow_duplicate` | the given fields; `set_posting_time` 1 when `posting_date` is given; `payment_terms_template` "" when `due_date` is given (REQ-001-PRS-F017); `taxes` from the template; `company`; `docstatus` 0 |
| `update_draft_sales_invoice` | **`name`**, **`modified`**; at least one of `posting_date`, `due_date`, `items`, `taxes_and_charges`, `remarks` | the given fields; `set_posting_time` 1 when `posting_date` is given; `payment_terms_template`, `payment_schedule` and `due_date` as REQ-001-PRS-F017 says; `taxes` when `taxes_and_charges` is given (none when it is cleared); `modified` |

- Clearable on update: `remarks`, `taxes_and_charges` (with its rows).
- The customer isn't changed by an update: ERPNext would keep the first customer's address, payment terms, price list and receivable account. A draft for another customer is a new draft.
- A row without `rate` gets the rate ERPNext sets from the price list and its pricing rules, as in the form. Enterich never sends `ignore_pricing_rule`, so a site's pricing rules apply to every row; REQ-001-PRS-F016 warns where they replaced a given rate.
- Results add: `customer`, `posting_date`, `due_date`, `currency`, `net_total`, `total_taxes_and_charges`, `grand_total`, `taxes` \[`account_head`, `rate`, `tax_amount`\], `items` \[`item_code`, `qty`, `rate`, `amount`, `is_free_item`\].

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_sales_return` | **`return_against`**; `items` (1–20) \[**`item_code`**, **`qty`**\]; `posting_date` (default today, sent either way); `remarks`; `allow_duplicate` | ERPNext's return of `return_against` (`make_sales_return`), without `name`, `owner` and the fields starting with `__`, in its rows too; with `items`, only the rows of the given items, at the given quantities; `posting_date`, `set_posting_time` 1, and the invoice's `posting_time` when `posting_date` is the invoice's; `remarks` when given; `company`; `docstatus` 0 |
| `update_draft_sales_return` | **`name`**, **`modified`**; at least one of `items`, `posting_date`, `remarks` | `items` as for create, from ERPNext's return of the draft's `return_against`; `posting_date` with `set_posting_time` 1, and `posting_time` as for create; `remarks`; `modified` |

- `qty` is the quantity returned, as a positive number; Enterich sends it negative, as a return holds it. An item on several rows of the invoice is taken from them in row order, its paid rows before its free-item rows, each up to what is left to return on it. What is left is the invoice's quantity less the submitted returns against it, rounded to 9 decimal places; draft returns don't count.
- A fixed discount is a `discount_amount` without `additional_discount_percentage`; a fixed charge is a tax row of charge type Actual, such as shipping or tax withholding. ERPNext's return credits both in full, whatever is returned, so Enterich drafts only a return of the whole invoice for such an invoice; a person makes a partial one in ERPNext. A discount given as a percentage is counted anew from the return's total.
- The customer, the rates, the accounts and the taxes come from the invoice. An update doesn't change `return_against`: a return against another invoice is a new draft. Clearable on update: `remarks`.
- ERPNext keeps a credit note's outstanding amount on the credit note itself (`update_outstanding_for_self`), to be set against the invoice or paid back; a person can untick it before submitting, so that the invoice's outstanding amount is lowered instead.
- A return is a sales invoice: it counts towards the limit of drafts per hour with the sales invoices, and lists show it among them with `is_return` true.
- Results add what a sales invoice draft's do, and `return_against`.

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| customers | Customer; Address through its Dynamic Link to the customer | — | `name` |
| sales invoices | Sales Invoice | `company` | `posting_date` desc, `name` desc |
| `list_sales_tax_templates` | Sales Taxes and Charges Template | `company` | `name` |
| `report_accounts_receivable` | Accounts Receivable | `company`, `report_date`, `party_type` Customer, `party` (a list holding `customer`, when given), `ageing_based_on` (`Due Date` or `Posting Date`), `age_as_on` `Report Date`, `range` `30, 60, 90, 120` | ERPNext's |
| duplicate check | Sales Invoice, with `name`, `items.item_code`, `items.qty` and `items.is_free_item` (one row per item) in one call | `company`, `docstatus` 0, `customer`, `posting_date` | — |
| sales returns | the invoice with `frappe.client.get`; its return with `erpnext.accounts.doctype.sales_invoice.sales_invoice.make_sales_return` (`source_name`) | — | — |
| duplicate check of a sales return | Sales Invoice | `company`, `docstatus` 0, `is_return` 1, `return_against` | `name` |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_customers`, `get_customer` | Customer, Address: read |
| `list_sales_invoices`, `get_sales_invoice` | Sales Invoice: read |
| `list_sales_tax_templates` | Sales Taxes and Charges Template: read |
| `report_accounts_receivable` | Sales Invoice: read, report; Journal Entry: read (the report lists them for due dates; with select only, they arrive without); the role added to the Accounts Receivable report |
| `create_draft_sales_invoice`, `update_draft_sales_invoice` | Sales Invoice: read, create, write only if creator; Address, Item, Sales Taxes and Charges Template: read (ERPNext or Enterich reads them while saving); Account, Customer: select (ERPNext lists the accounts and checks the customer for the party's details) |
| `create_draft_sales_return`, `update_draft_sales_return` | Sales Invoice: read, create, write only if creator; Address, Item: read (ERPNext reads them while saving); Account, Customer: select (ERPNext lists the accounts and checks the customer for the party's details) |

The DocTypes a draft only links to, such as its company, currency, units, price list, payment terms, project or cost centres, need no right: ERPNext checks a link without the user's permissions.

A return update giving `items` needs create on Sales Invoice too: ERPNext maps the return of the invoice as a new document (`get_mapped_doc`).

Enterich's comment on a draft, with its warnings, needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- Customers, sales invoices, sales tax templates and receivables are readable as catalogued, for the assigned company only.
- Sales invoice drafts are created and updated with exactly the catalogued fields; a posting date given is kept.
- Credit notes are drafted from the invoice's own return, for all or some of its items, never above what is left to return, and never crediting a fixed discount or charge in full for part of an invoice.
- A repeated sales invoice create is refused as a possible duplicate unless the agent allows it.

## Assumptions

Checked against ERPNext v16.52 source:

- An invoice saved with `set_posting_time` 0 gets today, in the site's time zone (System Settings), as posting date at every save.
- Saving through `/api/resource` runs `set_missing_values`: customer name, currency, price list, accounts and the customer's payment terms template are filled in. POST and PUT answer with the saved document under `data`.
- A row saved without a rate, or at 0, gets the price list rate with the pricing rules applied. A given rate is kept unless a price pricing rule matches the row; then the rule sets the rate anew at every save and its name goes into the row's `pricing_rules`. Product pricing rules append free-item rows (`is_free_item`).
- The customer's address, contact, payment terms, price list and accounts are filled in on save only where the draft has none (`update_if_missing`); a customer address of another customer is refused (`validate_party_address_and_contact`).
- ERPNext looks up prices and pricing rules without a permission check, and creates or changes an Item Price from a draft only for a user with write on Item Price; the agent user has none.
- A due date before the posting date, or later than the payment terms allow, is refused on save unless the user is a credit controller.
- ERPNext adds a template's tax rows on save only when Accounts Settings say so (`add_taxes_from_taxes_and_charges_template`); Enterich therefore sends them itself.
- A PUT carrying `modified` is refused with `TimestampMismatchError` when the stored draft has another; rows given in a PUT replace the stored ones.
- Without `age_as_on`, Accounts Receivable ages from today whatever the report date; without `range`, it uses 30, 60, 90, 120. It appends a total row as a list, and a prepared report answers with `prepared_report` set, with an earlier run's rows or none. It reads Sales Invoice and Journal Entry through permission-checked lists, Payment Ledger Entry without a permission check.
- A list call can filter Address by its Dynamic Link rows, and can return Sales Invoice Item fields, one row per item.
- `make_sales_return` maps a submitted sales invoice to an unsaved return (`make_return_doc`), and refuses one that isn't submitted: `is_return` 1, `return_against`, `ignore_pricing_rule` 1, `update_outstanding_for_self` 1; each row at the invoice's rate, its quantity less what submitted returns took back, negative, linked to its invoice row (`sales_invoice_item`); the invoice's taxes. It needs read on the invoice and create on Sales Invoice (`get_mapped_doc`).
- `make_return_doc` negates the invoice's whole `discount_amount` and the amount of every tax row of charge type Actual, whatever is returned; with `additional_discount_percentage`, the totals count the discount anew from the return's total. Tax withholding rows are of charge type Actual.
- The return's quantity left is the invoice row's less the returned, in floating point without rounding (0.3 less 0.1 is 0.19999999999999998); `validate_return` rounds both to the field's precision before comparing.
- A return's `posting_time` isn't copied from the invoice (`no_copy`): it gets the time of the mapping.
- On save, a return is refused when its customer isn't the invoice's, its posting date and time are before the invoice's, a row's rate is above the invoice's, a row returns more than is left (submitted returns counted, drafts not), or no row has a negative quantity (`validate_return`). Frappe sets a new document's `owner` to the session user, whatever the body says.

Checked on a real ERPNext v16 site by hand (2026-11-03):

- `make_sales_return` for a submitted invoice of two items at 50 and 19 % VAT returned the whole invoice at −119; with the row cut to one item and the fields starting with `__`, `name` and `owner` left out, it saved as a draft return at −59.5. ERPNext emptied the payment schedule the return took from the invoice. For an invoice that doesn't exist, it fails with a `TypeError` rather than an answer naming it.

Checked on a real ERPNext v16 site by hand (2026-11-04):

- A submitted invoice of two rows at 2 × 50, with a fixed discount of 10 and a charge of type Actual of 20, returned at one item of one row saved at a net total of −40 and a grand total of −60: the whole discount and charge credited, not a share. Its return carried the time of the mapping as posting time, earlier in the day than the invoice's.

Checked on a real ERPNext v16 site by the end-to-end test:

- The rights in the Rights section suffice, and each is needed (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
