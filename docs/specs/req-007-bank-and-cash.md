# REQ-007: Enterich Bank and Cash — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations on the assigned company's bank accounts: the accounts themselves, the bank transactions imported from statements, and the payment entries that settle invoices. Read only: the agent finds unreconciled bank lines and the payments behind them, and uses them to prepare journal entries (REQ-006) or to answer questions.

Out of scope: payment entry drafts, reconciliation, importing statements; bank accounts of parties.

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-007-P1-1. As the operator, I need the agent to show me which bank lines aren't reconciled yet and which payments exist, so that I can clear them quickly.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## Terms

- **Reconciled**: a submitted bank transaction whose amount is fully allocated to vouchers (`unallocated_amount` 0 or less, as ERPNext sets its status).
- **Pending**: a bank transaction still a draft, as a statement import leaves its lines unless it submits them; bank reconciliation doesn't offer it.

## URS — Functional

#### REQ-007-URS-F001: Read bank and cash

**Description**: The agent SHALL be able to read the company's own bank accounts, its bank transactions with their allocations, and its payment entries with their references.

**Related User Stories**: REQ-007-P1-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: Unreconciled lines are the bookkeeping work still open at the bank.

## PRS — Functional

#### REQ-007-PRS-F001: Bank accounts

**Description**: Enterich SHALL offer `list_bank_accounts` as the catalogue below defines it, returning only the company's own accounts.

**Related URS**: REQ-007-URS-F001

**Definition of Done**:

- A party's bank account of the same company isn't returned.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-007-PRS-F002: Bank transactions

**Description**: Enterich SHALL offer `list_bank_transactions` and `get_bank_transaction` as the catalogue below defines them, with the bank transaction states below.

**Related URS**: REQ-007-URS-F001

**Definition of Done**:

- Each `state` sends exactly its ERPNext filter; without `state`, only unreconciled transactions are returned (this spec's default, see REQ-001's States).
- A pending transaction is returned for `pending` and `all`, never for `unreconciled` or `reconciled`.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-007-PRS-F003: Payment entries

**Description**: Enterich SHALL offer `list_payment_entries` and `get_payment_entry` as the catalogue below defines them.

**Related URS**: REQ-007-URS-F001

**Definition of Done**:

- `payment_type`, `party_type` and `state` each send exactly their ERPNext filter; `party` requires `party_type`.
- Verification: test.
- Evidence: Enterich's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_bank_accounts` | `include_disabled`, `limit`, `offset` | `name`, `account_name`, `bank`, `account`, `iban`, `bank_account_no`, `is_default`, `disabled` |
| `list_bank_transactions` | `bank_account`, `state` (unreconciled, reconciled, pending, all; default unreconciled), `from_date`, `to_date`, `limit`, `offset` | `name`, `date`, `bank_account`, `deposit`, `withdrawal`, `included_fee`, `currency`, `unallocated_amount`, `status`, `party_type`, `party`, *`description`*, *`reference_number`*, *`transaction_type`*, *`bank_party_name`*, *`bank_party_iban`*, *`bank_party_account_number`* |
| `get_bank_transaction` | **`name`** | as above, plus `modified`, `payment_entries` \[`payment_document`, `payment_entry`, `allocated_amount`\], `url`, `truncated` |
| `list_payment_entries` | `payment_type` (Receive, Pay, Internal Transfer), `party_type` (Customer, Supplier), `party`, `state` (draft, submitted, cancelled), `from_date`, `to_date`, `limit`, `offset` | `name`, `payment_type`, `posting_date`, `party_type`, `party`, *`party_name`*, `paid_amount`, `received_amount`, `paid_from_account_currency`, `paid_to_account_currency`, `mode_of_payment`, *`reference_no`*, `reference_date`, `bank_account`, `unallocated_amount`, `clearance_date`, `docstatus`, `modified` |
| `get_payment_entry` | **`name`** | as above, plus `paid_from`, `paid_to`, `references` \[`reference_doctype`, `reference_name`, `allocated_amount`\], *`remarks`*, `url`, `truncated` |

Bank transaction `state`: `unreconciled` is `docstatus` 1 with `unallocated_amount` > 0, `reconciled` is `docstatus` 1 with `unallocated_amount` ≤ 0, `pending` is `docstatus` 0, `all` is `docstatus` < 2 (cancelled ones left out).

A bank transaction's `party_type` and `party` are the party set on the line, by hand or by ERPNext's party matching where the site turns it on; it may be an Employee. `included_fee` is the bank's fee: part of a withdrawal, or already deducted from a deposit. An allocation's `payment_document` names the DocType of its `payment_entry`: Payment Entry, Journal Entry, Sales Invoice, Purchase Invoice or Bank Transaction. A payment entry's `clearance_date` is empty until bank reconciliation matches it; `unallocated_amount` is the part not allocated to invoices, such as an advance.

`party` requires `party_type`; payment entries of other party types (Employee, Shareholder) come back in results but can't be filtered by party. `reference_doctype` and `payment_document` are ERPNext's values in a result, never an input.

### ERPNext calls

| Operations | DocType | Fixed filters | Order |
| :- | :- | :- | :- |
| `list_bank_accounts` | Bank Account | `company`, `is_company_account` 1 | `name` |
| bank transactions | Bank Transaction | `company` | `date` desc, `name` desc |
| payment entries | Payment Entry | `company` | `posting_date` desc, `name` desc |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_bank_accounts` | Bank Account: read |
| `list_bank_transactions`, `get_bank_transaction` | Bank Transaction: read |
| `list_payment_entries`, `get_payment_entry` | Payment Entry: read |

## Acceptance Criteria Summary

- The company's own bank accounts, its bank transactions and its payment entries are readable as catalogued, for the assigned company only.
- Unreconciled bank transactions are the default view.
- Bank transaction texts and counter-party details arrive only under `outside_text`.

## Assumptions

Checked against ERPNext v16.52 source:

- A bank transaction's `company` is fetched from its bank account and is read-only.
- A company bank account (`is_company_account`) needs a company and a non-group account of type Bank of that company; its name is the account name and the bank (`account_name - bank`).
- A bank transaction's `status` is Pending as a draft; on submit and every allocation ERPNext sets Unreconciled while `unallocated_amount` > 0, otherwise Reconciled; Cancelled on cancel (`set_status`). `unallocated_amount` is the difference of `withdrawal` and `deposit`, as a positive amount, less the allocations.
- The Bank Statement Import based on Data Import submits its transactions only with "Submit After Import" and otherwise leaves drafts; the Bank Statement Import Log, the bank transaction upload and Plaid submit them. The bank reconciliation tool offers only submitted transactions.
- On submit, and only with Accounts Settings' `enable_party_matching` (off by default), ERPNext matches a transaction's party from the counterparty's account number or IBAN, among parties' bank accounts and employees, and with `enable_fuzzy_matching` also from the name and description (`auto_set_party`); a party set by hand stays. A transaction's amount can be allocated to the DocTypes of the `bank_reconciliation_doctypes` hook (Payment Entry, Journal Entry, Sales Invoice, Purchase Invoice) and to another bank transaction.
- Bank reconciliation sets the `clearance_date` of the voucher a transaction is allocated to, such as a payment entry; nothing sets the allocation row's own `clearance_date`, so Enterich doesn't return it.

Not checked yet:

- The rights in the Rights section are the minimum; the integration test proves them (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
