# REQ-007: Enterich Bank and Cash — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations on the assigned company's bank accounts: the accounts themselves, the bank transactions imported from statements, and the payment entries that settle invoices. The agent finds unreconciled bank lines and the payments behind them, prepares payment entry drafts for payments received from customers and made to suppliers through the company's bank accounts, and uses the lines to prepare journal entries (REQ-006) or to answer questions.

Out of scope: reconciliation, importing statements; bank accounts of parties; payment entries through cash accounts, internal transfers, refunds (a payment to a customer or from a supplier), payments between two currencies, deductions such as a discount or a bank fee, allocations to anything but invoices, allocations to an invoice's payment terms, invoices booked to another receivable or payable account than the party's, and payments to a supplier held for payments.

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-007-P1-1. As the operator, I need the agent to show me which bank lines aren't reconciled yet and which payments exist, so that I can clear them quickly.
- REQ-007-P3-1. As the bookkeeper, I need the agent to turn a payment on the bank statement into a payment entry draft against the invoices it pays, and to notice when that payment is already recorded, so that I only review and submit.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## Terms

- **Reconciled**: a submitted bank transaction whose amount is fully allocated to vouchers (`unallocated_amount` 0 or less, as ERPNext sets its status).
- **Pending**: a bank transaction still a draft, as a statement import leaves its lines unless it submits them; bank reconciliation doesn't offer it.
- **Allocation**: the part of a payment set against one invoice; the part of the payment not allocated is an advance to or from the party.

## URS — Functional

#### REQ-007-URS-F001: Read bank and cash

**Description**: The agent SHALL be able to read the company's own bank accounts, its bank transactions with their allocations, and its payment entries with their references.

**Related User Stories**: REQ-007-P1-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: Unreconciled lines are the bookkeeping work still open at the bank.

#### REQ-007-URS-F002: Prepare payments

**Description**: The agent SHALL be able to create and change drafts of payment entries for payments received from customers and made to suppliers through the company's bank accounts, allocated to the party's invoices, and a payment already recorded SHALL NOT be recorded again unnoticed.

**Related User Stories**: REQ-007-P3-1 | **Refines**: REQ-001-URS-F002, REQ-001-URS-F007 | **Rationale**: An invoice stays open until its payment is booked; the bank's reference number ties a payment to its statement line.

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

#### REQ-007-PRS-F004: Payment entry drafts

**Description**: Enterich SHALL offer `create_draft_payment_entry` and `update_draft_payment_entry` as the catalogue below defines them. It SHALL take the payment type and the invoices' DocType from the party type, and the bank's ledger account from `bank_account`, which SHALL be an enabled bank account of the assigned company's own (as `list_bank_accounts` returns them). It SHALL refuse an update of a draft that isn't a payment received from a customer or made to a supplier as for another company's document, before its state and `modified` are checked.

**Related URS**: REQ-007-URS-F002

**Definition of Done**:

- A create for a customer sends `payment_type` Receive, the bank account's ledger account as `paid_to`, `received_amount` equal to `paid_amount`, and its references as Sales Invoice; one for a supplier sends Pay, the ledger account as `paid_from`, and its references as Purchase Invoice.
- A create without `posting_date` sends today in the configured time zone, and without `reference_date` the posting date.
- A bank account of another company, a party's bank account and a disabled one are each refused naming `bank_account`, without a write.
- An update of an internal transfer, or of a payment made to a customer, is refused without a write, with the answer for a name that doesn't exist or isn't permitted (REQ-001-PRS-F009), also when it is submitted or its `modified` is stale.
- An update giving `bank_account` sends its ledger account in the field of the draft's payment type, with that side's account currency and type empty; one giving `paid_amount` sends it as `received_amount` too; one giving `references` sends the party side's account, its currency and its type empty, and as an empty list leaves the draft without references.
- At a company that books advances in a separate party account, a draft created without references gets the advance account, and an update giving references to invoices gets the party's receivable or payable account.
- Verification: test.
- Evidence: Enterich's test suite; the end-to-end test against a real ERPNext v16 site.

#### REQ-007-PRS-F005: Payment entry rules

**Description**: Before saving, Enterich SHALL refuse a payment entry create or update whose resulting draft breaks a rule, naming the input:

- each invoice in `references` appears once and is a submitted invoice of the assigned company for the draft's party, not a return, not on hold (a purchase invoice), with an outstanding amount;
- each `allocated_amount` is at most its invoice's outstanding amount;
- the allocations together are at most the paid amount: the given references, or when an update gives none, the draft's as saved; the given `paid_amount`, or the draft's.

**Related URS**: REQ-007-URS-F002, REQ-001-URS-F006

**Definition of Done**:

- A reference to a draft, a cancelled, a paid or a return invoice, to a purchase invoice on hold, to another party's invoice or to one that doesn't exist for the assigned company is refused naming `references` and the invoice, without a write; so is an invoice given twice.
- An `allocated_amount` above the invoice's outstanding amount is refused naming the invoice and its outstanding amount.
- Allocations above `paid_amount` are refused naming both sums; so is an update lowering `paid_amount` below the draft's saved allocations.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-007-PRS-F006: Duplicate match for payment entries

**Description**: For REQ-001-PRS-F005, a payment entry create SHALL match a draft or submitted payment entry of the assigned company with the same party type, party and `reference_no`. An update that gives a `reference_no` SHOULD carry a warning, added to the draft, when another draft or submitted payment entry of the assigned company has the same party and `reference_no`.

**Related URS**: REQ-007-URS-F002

**Definition of Done**:

- A create matching a draft or a submitted payment entry is refused naming it; a cancelled one doesn't count, and the same `reference_no` for another party goes through.
- An update to the `reference_no` of another payment entry of the party saves, with a warning naming it.
- Verification: test.
- Evidence: Enterich's test suite.

#### REQ-007-PRS-F007: Payment warnings

**Description**: A payment entry create or update result SHOULD carry a warning, added to the draft (REQ-001-PRS-F015):

- when the draft has references and part of its paid amount isn't allocated, naming the amount: ERPNext books it as an advance;
- when the bank's ledger account and the party's account have different currencies, naming both: the draft's `received_amount` equals `paid_amount` and its exchange rates may not match the accounts.

**Related URS**: REQ-007-URS-F002, REQ-001-URS-F009

**Definition of Done**:

- A payment of 30 with 20 allocated returns a warning naming 10; one fully allocated, and one without references, returns none.
- A draft saved with `paid_from_account_currency` other than `paid_to_account_currency` returns a warning naming both currencies.
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

### Drafts

| Operation | Inputs | Sent to ERPNext |
| :- | :- | :- |
| `create_draft_payment_entry` | **`party_type`** (Customer, Supplier), **`party`**; **`bank_account`**; **`paid_amount`**; **`reference_no`**, `reference_date` (default `posting_date`); `posting_date` (default today, sent either way); `references` (0–20) \[**`reference_name`**, **`allocated_amount`**\]; `allow_duplicate` | `payment_type` Receive for a customer, Pay for a supplier; `party_type`, `party`; `bank_account`, and its ledger account as `paid_to` (Receive) or `paid_from` (Pay); `paid_amount`, and the same amount as `received_amount`; `reference_no`, `reference_date`, `posting_date`; `references` with `reference_doctype` Sales Invoice (Receive) or Purchase Invoice (Pay); `company`; `docstatus` 0 |
| `update_draft_payment_entry` | **`name`**, **`modified`**; at least one of `bank_account`, `paid_amount`, `reference_no`, `reference_date`, `posting_date`, `references` | the given fields, mapped as for create; with `bank_account`, the bank side's `paid_to_account_currency` and `paid_to_account_type` (Receive) or `paid_from_…` (Pay) empty, which ERPNext then reads from the new account; with `references`, the party side's account, `paid_from`, `paid_from_account_currency` and `paid_from_account_type` (Receive) or `paid_to…` (Pay), empty, which ERPNext then sets again for the references; `modified` |

- `reference_no` is the bank's reference for the payment, as on the statement: a string of 1–140 characters without leading or trailing whitespace, not a name. ERPNext requires it and `reference_date` for a payment through a bank account.
- `paid_amount` and `allocated_amount` are more than 0 and at most 1,000,000,000, with at most 2 decimal places: ERPNext keeps an amount as given but rounds the totals to the currency's precision, so a third decimal place would leave a difference. The bank account and the party's account are in one currency, so Enterich sends it as `received_amount` too (REQ-007-PRS-F007 warns otherwise).
- References given in an update replace all existing ones; an empty list removes them. An update giving only `posting_date` leaves `reference_date` as it is: the bank's date doesn't follow the posting date. The party isn't changed by an update: ERPNext would keep the first party's account. A payment from another party is a new draft.
- ERPNext fills in the party's name and its receivable or payable account, the exchange rates, each invoice's outstanding amount, the allocated and unallocated amounts, and the remarks.
- Results add: `payment_type`, `posting_date`, `party_type`, `party`, `bank_account`, `paid_from`, `paid_to`, `paid_amount`, `received_amount`, `paid_from_account_currency`, `paid_to_account_currency`, *`reference_no`*, `reference_date`, `total_allocated_amount`, `unallocated_amount`, `references` \[`reference_doctype`, `reference_name`, `allocated_amount`, `outstanding_amount`\].

### ERPNext calls

| Operations | DocType | Fixed filters | Order |
| :- | :- | :- | :- |
| `list_bank_accounts` | Bank Account | `company`, `is_company_account` 1 | `name` |
| bank transactions | Bank Transaction | `company` | `date` desc, `name` desc |
| payment entries | Payment Entry | `company` | `posting_date` desc, `name` desc |
| a draft's bank account | Bank Account, its `account`, `company`, `is_company_account` and `disabled` | — | — |
| a draft's references | Sales Invoice or Purchase Invoice, with `name`, `customer` or `supplier`, `docstatus`, `is_return` and `outstanding_amount` | `company`, `name` among the given invoices | — |
| duplicate check | Payment Entry | `company`, `docstatus` 0 or 1, `party_type`, `party`, `reference_no`; on update also `name` other than the draft | — |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_bank_accounts` | Bank Account: read |
| `list_bank_transactions`, `get_bank_transaction` | Bank Transaction: read |
| `list_payment_entries`, `get_payment_entry` | Payment Entry: read |
| `create_draft_payment_entry`, `update_draft_payment_entry` | Payment Entry: read, create, write only if creator; Account: select; Bank Account, Customer, Sales Invoice, Supplier, Purchase Invoice: read (Enterich and ERPNext read them while saving: Account for a new bank account, Customer and Sales Invoice for a customer's payment, Supplier and Purchase Invoice for a supplier's) |

ERPNext lists a payment's accounts with the user's permissions when it reads their currency and type (`get_account_details`), hence select on Account; the party's receivable or payable account and the invoices' accounts need nothing more.

Enterich's comment on a draft, with its warnings, needs no further right (REQ-001-PRS-F015).

## Acceptance Criteria Summary

- The company's own bank accounts, its bank transactions and its payment entries are readable as catalogued, for the assigned company only.
- Unreconciled bank transactions are the default view.
- Bank transaction texts and counter-party details arrive only under `outside_text`.
- A payment received from a customer or made to a supplier through one of the company's bank accounts can be drafted and corrected, allocated to the party's open invoices; a payment with the same bank reference already recorded for the party is refused unless the agent allows it.

## Assumptions

Checked against ERPNext v16.52 source:

- A bank transaction's `company` is fetched from its bank account and is read-only.
- A company bank account (`is_company_account`) needs a company and a non-group account of type Bank of that company; its name is the account name and the bank (`account_name - bank`).
- A bank transaction's `status` is Pending as a draft; on submit and every allocation ERPNext sets Unreconciled while `unallocated_amount` > 0, otherwise Reconciled; Cancelled on cancel (`set_status`). `unallocated_amount` is the difference of `withdrawal` and `deposit`, as a positive amount, less the allocations.
- The Bank Statement Import based on Data Import submits its transactions only with "Submit After Import" and otherwise leaves drafts; the Bank Statement Import Log, the bank transaction upload and Plaid submit them. The bank reconciliation tool offers only submitted transactions.
- On submit, and only with Accounts Settings' `enable_party_matching` (off by default), ERPNext matches a transaction's party from the counterparty's account number or IBAN, among parties' bank accounts and employees, and with `enable_fuzzy_matching` also from the name and description (`auto_set_party`); a party set by hand stays. A transaction's amount can be allocated to the DocTypes of the `bank_reconciliation_doctypes` hook (Payment Entry, Journal Entry, Sales Invoice, Purchase Invoice) and to another bank transaction.
- Bank reconciliation sets the `clearance_date` of the voucher a transaction is allocated to, such as a payment entry; nothing sets the allocation row's own `clearance_date`, so Enterich doesn't return it.
- A payment entry checks that `paid_amount` and `received_amount` are given before it counts them (`validate_mandatory` before `set_amounts`), so a draft without `received_amount` is refused; between two accounts of one currency ERPNext sets `received_amount` to `paid_amount` afterwards. It fills the party's account from the party or the company (`get_party_account`), each account's currency and type only while they are empty (`set_missing_values`, through `get_account_details`, which lists the account with the user's permissions), and each reference's outstanding amount from the invoice (`set_missing_ref_details`), and refuses an allocation above the invoice's outstanding amount as of now, an invoice of another party, and one not submitted. It requires `reference_no` and `reference_date` when the bank side's account is of type Bank (`validate_transaction_reference`).
- With the company's `book_advance_payments_in_separate_party_account`, a draft without references to invoices gets the company's advance account as the party's account (`set_liability_account`); one with them keeps the party's account it has, and ERPNext refuses an invoice booked to another account ("is associated with …, but Party Account is …") and a purchase invoice on hold.
- A draft payment entry doesn't lower an invoice's outstanding amount; only its submit does. Two drafts can therefore allocate the same open amount; the duplicate check by the bank's reference catches the same payment entered twice.

Checked on a real ERPNext v16 site by hand (2026-11-03):

- A payment entry inserted through `/api/resource` with the party, `paid_to` and `bank_account`, both amounts, the bank's reference and its date, and a reference to a submitted sales invoice saves as a draft with the party's account, exchange rate 1, the invoice's outstanding amount and the unallocated rest filled in. Without `received_amount` it is refused ("Received Amount is mandatory").
- A paid amount of 10.005 is kept as given, while `base_paid_amount` is 10.0, and an allocation of 3.335 gives `total_allocated_amount` 3.34.
- With advances booked in a separate party account, a draft made without references gets the advance account; an update adding a reference to an invoice is refused, unless it sends `paid_from`, `paid_from_account_currency` and `paid_from_account_type` empty: then ERPNext sets the party's receivable account.

Checked on a real ERPNext v16 site by the end-to-end test:

- The rights in the Rights section suffice, and each is needed (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
