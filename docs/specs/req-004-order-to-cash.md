# REQ-004: Enterich Order to Cash — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations of the selling side of the assigned company: customers, sales invoices, sales tax templates and open receivables. The agent reads them and prepares drafts of sales invoices, which a person reviews and submits.

Out of scope: quotations, sales orders and delivery notes; returns (credit notes) as drafts; payments, which belong to bank and cash (REQ-007).

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-004-P1-1. As the operator, I need the agent to tell me which customers owe what and since when, so that I can follow up without searching lists.
- REQ-004-P3-1. As the bookkeeper, I need the agent to prepare sales invoice drafts with the right customer, items and taxes, so that I only review and submit.

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
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site (backlog).

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

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| customers | Customer; Address through its Dynamic Link to the customer | — | `name` |
| sales invoices | Sales Invoice | `company` | `posting_date` desc, `name` desc |
| `list_sales_tax_templates` | Sales Taxes and Charges Template | `company` | `name` |
| `report_accounts_receivable` | Accounts Receivable | `company`, `report_date`, `party_type` Customer, `party` (a list holding `customer`, when given), `ageing_based_on` (`Due Date` or `Posting Date`), `age_as_on` `Report Date`, `range` `30, 60, 90, 120` | ERPNext's |
| duplicate check | Sales Invoice, with `name`, `items.item_code`, `items.qty` and `items.is_free_item` (one row per item) in one call | `company`, `docstatus` 0, `customer`, `posting_date` | — |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_customers`, `get_customer` | Customer, Address: read |
| `list_sales_invoices`, `get_sales_invoice` | Sales Invoice: read |
| `list_sales_tax_templates` | Sales Taxes and Charges Template: read |
| `report_accounts_receivable` | Sales Invoice: read, report; Journal Entry: read (the report lists them for due dates; with select only, they arrive without); the role added to the Accounts Receivable report |
| `create_draft_sales_invoice`, `update_draft_sales_invoice` | Sales Invoice: read, create, write; Customer, Address, Item, Account, Cost Center, Sales Taxes and Charges Template: read (ERPNext reads them while saving); Company, Currency, UOM, Price List, Payment Terms Template, Project: select |

Warnings are added to a draft as a comment, which needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- Customers, sales invoices, sales tax templates and receivables are readable as catalogued, for the assigned company only.
- Sales invoice drafts are created and updated with exactly the catalogued fields; a posting date given is kept.
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

Not checked yet:

- The rights in the Rights section are the minimum; the end-to-end test proves them (REQ-002-PRS-NF013).
- ERPNext computes `due_date` from the customer's payment terms when it isn't given (the template is filled in; the date computation runs through several validation steps).

## Open Questions

None at the moment.
