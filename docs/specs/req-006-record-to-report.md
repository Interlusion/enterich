# REQ-006: Erpel Record to Report — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations of the general ledger of the assigned company: the chart of accounts, cost centres, journal entries, the General Ledger and the Trial Balance. The agent reads them and prepares drafts of journal entries (accruals, corrections, reclassifications, bookings from a bank line), which a person reviews and submits.

Out of scope: drafts of journal entries of any voucher type other than Journal Entry; period closing; changing the chart of accounts or cost centres.

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-006-P1-1. As the operator, I need the agent to answer questions from the ledger and the trial balance, so that I see balances and movements without building reports.
- REQ-006-P3-1. As the bookkeeper, I need the agent to prepare balanced journal entry drafts with the right accounts, so that I only review and submit.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## URS — Functional

#### REQ-006-URS-F001: Read the ledger

**Description**: The agent SHALL be able to read the accounts and cost centres, the journal entries with their rows, and the General Ledger and Trial Balance of the assigned company.

**Related User Stories**: REQ-006-P1-1, REQ-006-P3-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: Every draft needs exact account and cost centre names.

#### REQ-006-URS-F002: Prepare journal entries

**Description**: The agent SHALL be able to create and change drafts of journal entries of the voucher type Journal Entry, and SHALL NOT change drafts of any other voucher type.

**Related User Stories**: REQ-006-P3-1 | **Refines**: REQ-001-URS-F002 | **Rationale**: The voucher type is a label: the accounts decide the booking, and a booking against a bank account is reconciled the same way whatever its type. Other types carry special meaning (Opening Entry, Inter Company Journal Entry) or are made by ERPNext itself.

## PRS — Functional

#### REQ-006-PRS-F001: Accounts and cost centres

**Description**: Erpel SHALL offer `list_accounts` and `list_cost_centers` as the catalogue below defines them.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- `root_type` sends exactly its filter; an account's number and name are both searchable.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-006-PRS-F002: Journal entry reads

**Description**: Erpel SHALL offer `list_journal_entries` and `get_journal_entry` as the catalogue below defines them.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- `voucher_type` accepts exactly ERPNext v16's voucher types (see the catalogue) and refuses any other value.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-006-PRS-F003: General Ledger

**Description**: Erpel SHALL offer `report_general_ledger` as the catalogue below defines it, for at most 366 days per call.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- A range over 366 days is refused before any ERPNext call.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Erpel's test suite; the integration test against a real ERPNext v16 site (backlog).

#### REQ-006-PRS-F004: Trial Balance

**Description**: Erpel SHALL offer `report_trial_balance` as the catalogue below defines it, finding the fiscal year from the dates itself.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- Dates in one fiscal year return its trial balance with `fiscal_year` named; dates in no fiscal year, or in two, are refused.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Erpel's test suite; the integration test against a real ERPNext v16 site (backlog).

#### REQ-006-PRS-F005: Journal entry drafts

**Description**: Erpel SHALL offer `create_draft_journal_entry` and `update_draft_journal_entry` as the catalogue below defines them, sending each row's `debit` and `credit` as `debit_in_account_currency` and `credit_in_account_currency`, and refusing an update of a draft whose voucher type isn't Journal Entry as for another company's document.

**Related URS**: REQ-006-URS-F002

**Definition of Done**:

- Rows arrive with the account-currency fields, and never with `debit` or `credit`.
- An update of a Bank Entry or Opening Entry draft is refused without a write, with the answer for a name that doesn't exist or isn't permitted (REQ-001-PRS-F009).
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-006-PRS-F006: Journal entry rules

**Description**: Before calling ERPNext, Erpel SHALL refuse a journal entry create or update whose resulting draft breaks a rule:

- each row has exactly one of `debit` and `credit` above 0;
- the rows' debits and credits are equal as exact decimals;
- `party` requires `party_type`; `reference_name` requires `reference_type`;
- `cheque_date` requires `cheque_no`.

Clearing `cheque_no` SHALL clear `cheque_date` too.

**Related URS**: REQ-006-URS-F002, REQ-001-URS-F006

**Definition of Done**:

- Each broken rule is refused naming the input and the rule; nothing reaches ERPNext.
- An update with `cheque_no` set to an empty string sends both `cheque_no` and `cheque_date` cleared.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-006-PRS-F007: Duplicate match for journal entries

**Description**: For REQ-001-PRS-F005, a journal entry create SHALL match a draft of the assigned company with the same posting date (the given one, or today) and the same rows (account, debit, credit, in any order).

**Related URS**: REQ-006-URS-F002, REQ-001-URS-F007

**Definition of Done**:

- A create matching an existing draft is refused naming it; one that differs in a row or the date goes through.
- Verification: test.
- Evidence: Erpel's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

### Reads

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_accounts` | `search` (ID, account name, account number), `root_type` (Asset, Liability, Equity, Income, Expense), `include_groups`, `include_disabled`, `limit`, `offset` | `name`, `account_number`, `account_name`, `root_type`, `account_type`, `parent_account`, `is_group`, `disabled` |
| `list_cost_centers` | `search` (ID, cost centre name, number), `include_groups`, `include_disabled`, `limit`, `offset` | `name`, `cost_center_number`, `cost_center_name`, `parent_cost_center`, `is_group`, `disabled` |
| `list_journal_entries` | `state` (draft, submitted, cancelled), `voucher_type` (one of ERPNext v16's voucher types, below), `from_date`, `to_date`, `limit`, `offset` | `name`, `voucher_type`, `posting_date`, `total_debit`, `total_credit`, *`user_remark`*, `docstatus`, `owner`, `modified` |
| `get_journal_entry` | **`name`** | as above, plus *`cheque_no`*, `cheque_date`, `accounts` \[`account`, `party_type`, `party`, `debit_in_account_currency`, `credit_in_account_currency`, `cost_center`, `reference_type`, `reference_name`, *`user_remark`*\], `url`, `truncated` |
| `report_general_ledger` | **`from_date`**, **`to_date`** (at most 366 days apart), `account`, `party_type` (Customer, Supplier), `party`, `voucher_no`, `limit`, `offset` | `opening`, rows \[`posting_date`, `account`, `debit`, `credit`, `balance`, `voucher_type`, `voucher_no`, `party_type`, `party`, *`against`*, *`remarks`*\], `totals`, `closing` |
| `report_trial_balance` | **`from_date`**, **`to_date`** (within one fiscal year), `show_zero_values` (default false), `limit`, `offset` | `fiscal_year`, rows \[`account`, `account_name`, `parent_account`, `is_group`, `opening_debit`, `opening_credit`, `debit`, `credit`, `closing_debit`, `closing_credit`\] |

`party` requires `party_type`. Party names are not in report rows; `get_customer` and `get_supplier` give them.

ERPNext v16's voucher types: Journal Entry, Inter Company Journal Entry, Bank Entry, Cash Entry, Credit Card Entry, Debit Note, Credit Note, Contra Entry, Excise Entry, Write Off Entry, Opening Entry, Depreciation Entry, Asset Disposal, Periodic Accounting Entry, Exchange Rate Revaluation, Exchange Gain Or Loss, Deferred Revenue, Deferred Expense.

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_journal_entry` | `posting_date` (default today); `cheque_no`, `cheque_date` (the bank's reference and its date, which help match the entry to the bank statement); `user_remark`; **`accounts`** (2–20) \[**`account`**, `debit`, `credit`, `party_type` (Customer, Supplier), `party`, `cost_center`, `reference_type` (Sales Invoice, Purchase Invoice), `reference_name`, `user_remark`\]; `allow_duplicate` | the given fields, with each row's `debit` and `credit` sent as `debit_in_account_currency` and `credit_in_account_currency`; `voucher_type` Journal Entry; `multi_currency` 0; `company`; `docstatus` 0 |
| `update_draft_journal_entry` | **`name`**, **`modified`**; at least one of `posting_date`, `cheque_no`, `cheque_date`, `user_remark`, `accounts` | the given fields, rows mapped as for create; `modified` |

- Clearable on update: `user_remark`, `cheque_no` (with `cheque_date`).
- Results add: `posting_date`, `total_debit`, `total_credit`, the row count; no `currency`, because a journal entry has none of its own.
- Further voucher types can be added later as a minor change ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| `list_accounts` | Account | `company` | `name` |
| `list_cost_centers` | Cost Center | `company` | `name` |
| journal entries | Journal Entry | `company` | `posting_date` desc, `name` desc |
| `report_general_ledger` | General Ledger | `company`, dates | ERPNext's |
| `report_trial_balance` | Fiscal Year (to find the year), Trial Balance | `company`, `fiscal_year`, dates | ERPNext's |
| duplicate check | Journal Entry | `company`, `docstatus` 0, `posting_date` | — |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_accounts` | Account: read |
| `list_cost_centers` | Cost Center: read |
| `list_journal_entries`, `get_journal_entry` | Journal Entry: read |
| `report_general_ledger` | GL Entry: read, report; the role added to the General Ledger report |
| `report_trial_balance` | GL Entry: read, report; Account, Fiscal Year: read; the role added to the Trial Balance report |
| `create_draft_journal_entry`, `update_draft_journal_entry` | Journal Entry: read, create, write; Account, Cost Center: read; Company, Customer, Supplier, Sales Invoice, Purchase Invoice: select (for parties and references in rows) |

Warnings are added to a draft as a comment, which needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- Accounts, cost centres, journal entries, the General Ledger and the Trial Balance are readable as catalogued, for the assigned company only.
- Journal entry drafts are balanced, of type Journal Entry, and carry exactly the catalogued fields; drafts of other types are never changed.
- A repeated journal entry create is refused as a possible duplicate unless the agent allows it.

## Assumptions

Checked against ERPNext v16.52 source:

- `debit` and `credit` on Journal Entry Account are read-only; the account-currency fields are the ones written.
- ERPNext refuses a reference date without a reference number, for every voucher type, and a Bank Entry without both.
- Bank reconciliation offers every submitted journal entry booked against the bank account and not yet cleared, whatever its voucher type (Opening Entry excepted).
- The voucher types listed in the catalogue are ERPNext v16's options.

Not checked yet:

- The rights in the Rights section are the minimum; the integration test proves them (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
