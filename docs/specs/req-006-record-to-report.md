# REQ-006: Enterich Record to Report — Requirement Specification

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

**Description**: Enterich SHALL offer `list_accounts` and `list_cost_centers` as the catalogue below defines them.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- `root_type` sends exactly its filter; an account's number and name are both searchable.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-006-PRS-F002: Journal entry reads

**Description**: Enterich SHALL offer `list_journal_entries` and `get_journal_entry` as the catalogue below defines them.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- `voucher_type` accepts exactly ERPNext v16's voucher types (see the catalogue) and refuses any other value.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-006-PRS-F003: General Ledger

**Description**: Enterich SHALL offer `report_general_ledger` as the catalogue below defines it, for at most 366 days per call, both dates included. It SHALL check a given `account` (of the assigned company) and `party` as name inputs (REQ-001-PRS-F009) before the report. It SHALL take ERPNext's opening, total and closing rows by their position, not their label; `opening` and `closing` come from ERPNext's rows, `totals` are Enterich's sums over all entries (REQ-001's ERPNext calls). It SHALL return each row's `balance` only when `account` or `party` is given, the only case in which ERPNext counts the balance before `from_date`, and SHALL name in `currency` the currency of the amounts: the account's or party's when ERPNext shows the amounts in it, else the company's.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- A range of 366 days, both dates included, is answered; one of 367 is refused before any ERPNext call.
- With `account` or `party` given, the rows' `balance` is ERPNext's; without either, it is null, and `opening` holds the opening entries.
- An account in another currency than the company's returns its amounts with that `currency`; otherwise `currency` is the company's.
- An unknown account, another company's account and an unknown party are refused naming the input, before the report.
- An answer whose first row or last two rows aren't summary rows (with a posting date) is refused as a faulty answer.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-006-PRS-F004: Trial Balance

**Description**: Enterich SHALL offer `report_trial_balance` as the catalogue below defines it, finding the fiscal year from the dates itself as ERPNext does: among enabled fiscal years, those assigned to the assigned company first, then those assigned to no company.

**Related URS**: REQ-006-URS-F001

**Definition of Done**:

- Dates in one fiscal year return its trial balance with `fiscal_year` named; dates in no fiscal year, or in two, are refused.
- A fiscal year assigned only to other companies doesn't count; one assigned to the company comes before one assigned to none.
- ERPNext's total row isn't among the rows; `totals` are Enterich's sums over the root accounts' rows, as decimals.
- Report filters and columns match ERPNext v16.
- Verification: test and inspection.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-006-PRS-F005: Journal entry drafts

**Description**: Enterich SHALL offer `create_draft_journal_entry` and `update_draft_journal_entry` as the catalogue below defines them, sending each row's `debit` and `credit` as `debit_in_account_currency` and `credit_in_account_currency`, sending `posting_date` on every create (ERPNext sets none itself), and refusing an update of a draft whose voucher type isn't Journal Entry as for another company's document, before its state and `modified` are checked. It SHALL refuse an update of a draft with `multi_currency` set: Enterich changes only journal entries in the company's currency.

**Related URS**: REQ-006-URS-F002

**Definition of Done**:

- Rows arrive with the account-currency fields, and never with `debit` or `credit`.
- A create without `posting_date` sends today in the configured time zone.
- An update of a Bank Entry or Opening Entry draft, or of another company's journal entry, is refused without a write, with the answer for a name that doesn't exist or isn't permitted (REQ-001-PRS-F009), also when it is submitted or its `modified` is stale.
- An update of a draft with `multi_currency` set is refused naming `name`, without a write.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-006-PRS-F006: Journal entry rules

**Description**: Before calling ERPNext, Enterich SHALL refuse a journal entry create or update whose resulting draft breaks a rule:

- each row has exactly one of `debit` and `credit` above 0;
- the rows' debits and credits are equal: given rows as exact decimals; when an update gives none, the draft's total debit and total credit as ERPNext saved them;
- `party_type` and `party` come together; `reference_type` and `reference_name` come together;
- `cheque_no` and `cheque_date` come together (ERPNext refuses a number without a date at every save, a date without a number on submit).

The rules on single rows apply to the given rows; ERPNext checks the saved ones itself. Clearing `cheque_no` SHALL clear `cheque_date` too.

**Related URS**: REQ-006-URS-F002, REQ-001-URS-F006

**Definition of Done**:

- Each broken rule is refused naming the input and the rule; nothing reaches ERPNext.
- An update with `cheque_no` set to an empty string sends both `cheque_no` and `cheque_date` cleared.
- An update giving `cheque_date` to a draft with a `cheque_no` goes through; giving it to a draft without one is refused.
- An update without `accounts` of a draft whose saved totals differ is refused naming `accounts` and both totals.
- An update of a draft with a `cheque_date` but no `cheque_no`, giving neither, is refused naming `cheque_no` and the saved date.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-006-PRS-F007: Duplicate match for journal entries

**Description**: For REQ-001-PRS-F005, a journal entry create SHALL match a draft of the assigned company with the same posting date (the given one, or today) and the same rows (account, debit, credit, in any order), comparing amounts as ERPNext stores them: a given amount matches a stored one that differs by at most 0.005, the most that rounding to the currency's precision moves it.

**Related URS**: REQ-006-URS-F002, REQ-001-URS-F007

**Definition of Done**:

- A create matching an existing draft is refused naming it; one that differs in a row or the date goes through.
- A create repeated with amounts of three decimal places, which ERPNext saved rounded to two, is refused naming the first draft.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-006-PRS-F008: Totals ERPNext rounded

**Description**: A journal entry create or update result SHOULD carry a warning, added to the draft (REQ-001-PRS-F015), when ERPNext saved total debit and total credit that differ: it rounds each row to the currency's precision and checks the balance only on submit.

**Related URS**: REQ-006-URS-F002, REQ-001-URS-F009

**Definition of Done**:

- Rows of 10.004 and 5.004 against 15.008, balanced as exact decimals, saved by ERPNext as 15.00 against 15.01 (each row rounded to two places), return a warning naming both totals as 15 and 15.01.
- A draft saved with equal totals returns no warning.
- Verification: test.
- Evidence: Enterich's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

### Reads

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_accounts` | `search` (ID, account name, account number), `root_type` (Asset, Liability, Equity, Income, Expense), `include_groups`, `include_disabled`, `limit`, `offset` | `name`, `account_number`, `account_name`, `root_type`, `account_type`, `parent_account`, `is_group`, `disabled` |
| `list_cost_centers` | `search` (ID, cost centre name, number), `include_groups`, `include_disabled`, `limit`, `offset` | `name`, `cost_center_number`, `cost_center_name`, `parent_cost_center`, `is_group`, `disabled` |
| `list_journal_entries` | `state` (draft, submitted, cancelled), `voucher_type` (one of ERPNext v16's voucher types, below), `from_date`, `to_date`, `limit`, `offset` | `name`, `voucher_type`, `posting_date`, `total_debit`, `total_credit`, *`user_remark`*, `docstatus`, `owner`, `modified` |
| `get_journal_entry` | **`name`** | as above, plus *`cheque_no`*, `cheque_date`, `accounts` \[`account`, `account_currency`, `party_type`, `party`, `debit_in_account_currency`, `credit_in_account_currency`, `cost_center`, `reference_type`, `reference_name`, *`user_remark`*\], `url`, `truncated` |
| `report_general_ledger` | **`from_date`**, **`to_date`** (at most 366 days, both included), `account`, `party_type` (Customer, Supplier), `party`, `voucher_no`, `limit`, `offset` | `opening`, rows \[`posting_date`, `account`, `debit`, `credit`, `balance`, `voucher_type`, `voucher_no`, `party_type`, `party`, *`against`*, *`remarks`*\], `totals`, `closing`, `currency`; `opening`, `totals` and `closing` each {`debit`, `credit`, `balance`}; `currency` the amounts' currency, the company's unless ERPNext switched to the account's or party's |
| `report_trial_balance` | **`from_date`**, **`to_date`** (within one fiscal year), `show_zero_values` (default false), `limit`, `offset` | `fiscal_year`, rows \[`account`, `account_name` (number and name, as ERPNext shows it), `parent_account`, `is_group`, `opening_debit`, `opening_credit`, `debit`, `credit`, `closing_debit`, `closing_credit`\], `totals` {`opening_debit`, `opening_credit`, `debit`, `credit`, `closing_debit`, `closing_credit`} |

`party` requires `party_type`. Party names are not in report rows; `get_customer` and `get_supplier` give them. A year of a busy ledger without `account` can exceed the answer limit (REQ-002-PRS-NF011); the operation's description says to narrow it by account.

ERPNext v16's voucher types: Journal Entry, Inter Company Journal Entry, Bank Entry, Cash Entry, Credit Card Entry, Debit Note, Credit Note, Contra Entry, Excise Entry, Write Off Entry, Opening Entry, Depreciation Entry, Asset Disposal, Periodic Accounting Entry, Exchange Rate Revaluation, Exchange Gain Or Loss, Deferred Revenue, Deferred Expense.

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_journal_entry` | `posting_date` (default today, sent either way); `cheque_no`, `cheque_date` (the bank's reference and its date, which help match the entry to the bank statement); `user_remark`; **`accounts`** (2–20) \[**`account`**, `debit`, `credit`, `party_type` (Customer, Supplier), `party`, `cost_center`, `reference_type` (Sales Invoice, Purchase Invoice), `reference_name`, `user_remark`\]; `allow_duplicate` | the given fields, with each row's `debit` and `credit` sent as `debit_in_account_currency` and `credit_in_account_currency`; `voucher_type` Journal Entry; `multi_currency` 0; `company`; `docstatus` 0 |
| `update_draft_journal_entry` | **`name`**, **`modified`**; at least one of `posting_date`, `cheque_no`, `cheque_date`, `user_remark`, `accounts` | the given fields, rows mapped as for create; `modified` |

- Clearable on update: `user_remark`, `cheque_no` (with `cheque_date`).
- Accounts are in the company's currency: Enterich sends `multi_currency` 0, and ERPNext refuses an account in another currency. A row with a receivable or payable account needs `party_type` and `party`; ERPNext saves a party on an account of another type but refuses it on submit, as the create's description says. A row with a reference carries the invoice's party and its receivable or payable account.
- Results add: `posting_date`, `total_debit`, `total_credit`, `row_count`; no `currency`, because a journal entry has none of its own, and no `status`, which ERPNext v16 doesn't give a journal entry (`docstatus` says it).
- Further voucher types can be added later as a minor change ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).

### ERPNext calls

| Operations | DocType or report | Fixed filters | Order |
| :- | :- | :- | :- |
| `list_accounts` | Account | `company` | `name` |
| `list_cost_centers` | Cost Center | `company` | `name` |
| journal entries | Journal Entry | `company` | `posting_date` desc, `name` desc |
| `report_general_ledger` | the given `account` and `party` (`frappe.client.get`), then General Ledger | `company`, `from_date`, `to_date`, `account` and `party` as one-item lists when given, `include_default_book_entries` 1, `show_remarks` 1; no `categorize_by` | ERPNext's |
| `report_trial_balance` | Fiscal Year with `companies.company` (one row per company row, at most 1,000), to find the year | `disabled` 0, `year_start_date` ≤ `from_date`, `year_end_date` ≥ `from_date` | `year_start_date` desc |
| `report_trial_balance` | Trial Balance | `company`, `fiscal_year`, `from_date`, `to_date`, `show_zero_values`, `with_period_closing_entry_for_opening` 1, `with_period_closing_entry_for_current_period` 1, `include_default_book_entries` 1, `show_net_values` 1, `show_group_accounts` 1 | ERPNext's |
| duplicate check | Journal Entry, with `name`, `accounts.account`, `accounts.debit_in_account_currency` and `accounts.credit_in_account_currency` (one row per account row) in one call | `company`, `docstatus` 0, `posting_date` | — |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_accounts` | Account: read |
| `list_cost_centers` | Cost Center: read |
| `list_journal_entries`, `get_journal_entry` | Journal Entry: read |
| `report_general_ledger` | GL Entry: read, report; Account: read (the `account` given); Customer, Supplier: read (the one of the `party` given); the role added to the General Ledger report |
| `report_trial_balance` | GL Entry: read, report; Fiscal Year: read; the role added to the Trial Balance report |
| `create_draft_journal_entry`, `update_draft_journal_entry` | Journal Entry: read, create, write |

The accounts, cost centres, parties and invoices a journal entry's rows link to need no right: ERPNext checks a link without the user's permissions.

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
- `posting_date` is mandatory and has no default on the server (the form sets today); a journal entry has no `set_posting_time`, so its posting date stays as saved.
- ERPNext checks the balance (`validate_total_debit_and_credit`) and the reference fields for a Bank Entry (`validate_cheque_info`) only on submit, so a draft saves unbalanced; at every save, `create_remarks` refuses a reference number without a date. Each row is rounded to the currency's precision before the totals are summed.
- With `multi_currency` 0, an account in another currency than the company's is refused (`validate_multi_currency`); in the company's currency, the account-currency amounts are the company-currency ones.
- A receivable or payable account needs a party, of a party type with the same account type (`validate_party`). A reference to a sales or purchase invoice must name a submitted invoice whose customer or supplier and receivable or payable account are the row's, and the rows' amounts on its paying side may not exceed its outstanding amount (`validate_reference_doc`, `validate_invoices`). A party on an account of another type than Receivable, Payable or Equity is refused only on submit, by the GL entry (`validate_account_party_type`). A `reference_type` without `reference_name` is dropped at save. Under perpetual inventory, a stock account can only be booked by stock transactions (`validate_stock_accounts`).
- A journal entry has no payment schedule; REQ-001-PRS-F017 doesn't apply.
- Reports answer in the agent user's language: the General Ledger's and Trial Balance's summary labels, the General Ledger's `party_type` and remarks are translated (configuration guide: English).
- The General Ledger without `categorize_by` returns one opening row, the entries, a total row and a closing row; the summary rows have no posting date and a quoted, translated label as `account`. `balance` is a running balance from the opening row. Only with `account` or `party` does it read entries before `from_date` into the opening; otherwise the opening holds only opening entries. Entries marked as opening (`is_opening`, as an Opening Entry or an opening invoice) count in the opening row, not among the entries, unless `show_opening_entries` is set, which would also list those dated after `to_date`. With an account or a single party in another currency than the company's, the amounts, opening and closing are in that currency, named in each row's `presentation_currency` (`set_account_currency`, `convert_to_presentation_currency`); otherwise `presentation_currency` is the company's currency (`get_columns`). An unknown account or party is refused without naming the input, and another company's account passes ERPNext's check with an empty ledger. `account` and `party` are lists; a group account includes its children. Without `include_default_book_entries`, entries of the company's default finance book are left out; without `show_remarks`, remarks are.
- The Trial Balance requires `fiscal_year` and moves dates outside it to its bounds with a message, without refusing. Without the desk's defaults (`with_period_closing_entry_for_opening`, `with_period_closing_entry_for_current_period`, `include_default_book_entries`, `show_net_values`, `show_group_accounts`, all 1) it leaves out period closing entries and group accounts and doesn't net opening and closing. Its rows end with an empty row (with `show_zero_values`) and a total row; the group flag is `is_group_account`, and `account_name` is "number - name".
- ERPNext finds a fiscal year among enabled ones, those assigned to the company first, then those assigned to none (`get_fiscal_years`).

Checked on a real ERPNext v16 site by the end-to-end test:

- The rights in the Rights section suffice, and each is needed (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
