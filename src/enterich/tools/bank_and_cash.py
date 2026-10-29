"""Bank and cash: the company's bank accounts, bank transactions and payment entries
(REQ-007)."""

from typing import Any, Literal, Self

from pydantic import model_validator

from enterich.shapes import (
    Day,
    Flag,
    Inputs,
    Limit,
    Name,
    Offset,
    cut_rows,
    cut_texts,
    form_url,
    in_order,
    page,
    rows_of,
    shape,
)
from enterich.tools import Context, Operation, get_named

BANK_ACCOUNT_FIELDS = (
    "name",
    "account_name",
    "bank",
    "account",
    "iban",
    "bank_account_no",
    "is_default",
    "disabled",
)
TRANSACTION_FIELDS = (
    "name",
    "date",
    "bank_account",
    "deposit",
    "withdrawal",
    "included_fee",
    "currency",
    "unallocated_amount",
    "status",
    "party_type",
    "party",
    "description",
    "reference_number",
    "transaction_type",
    "bank_party_name",
    "bank_party_iban",
    "bank_party_account_number",
)
# What the bank wrote, from the statement
TRANSACTION_OUTSIDE = frozenset(
    {
        "description",
        "reference_number",
        "transaction_type",
        "bank_party_name",
        "bank_party_iban",
        "bank_party_account_number",
    }
)
ALLOCATION_FIELDS = ("payment_document", "payment_entry", "allocated_amount")
# REQ-007's bank transaction states
TRANSACTION_STATES: dict[str, list[list[Any]]] = {
    "unreconciled": [["docstatus", "=", 1], ["unallocated_amount", ">", 0]],
    "reconciled": [["docstatus", "=", 1], ["unallocated_amount", "<=", 0]],
    "pending": [["docstatus", "=", 0]],
    "all": [["docstatus", "<", 2]],
}
PAYMENT_FIELDS = (
    "name",
    "payment_type",
    "posting_date",
    "party_type",
    "party",
    "party_name",
    "paid_amount",
    "received_amount",
    "paid_from_account_currency",
    "paid_to_account_currency",
    "mode_of_payment",
    "reference_no",
    "reference_date",
    "bank_account",
    "unallocated_amount",
    "clearance_date",
    "docstatus",
    "modified",
)
PAYMENT_DETAIL_FIELDS = ("paid_from", "paid_to", "remarks")
PAYMENT_OUTSIDE = frozenset({"party_name", "reference_no", "remarks"})
REFERENCE_FIELDS = ("reference_doctype", "reference_name", "allocated_amount")
PAYMENT_STATES = {"draft": 0, "submitted": 1, "cancelled": 2}


class ListBankAccounts(Inputs):
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class ListBankTransactions(Inputs):
    bank_account: Name | None = None
    state: Literal["unreconciled", "reconciled", "pending", "all"] = "unreconciled"
    from_date: Day | None = None
    to_date: Day | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _period(self) -> Self:
        in_order(self.from_date, self.to_date)
        return self


class GetBankTransaction(Inputs):
    name: Name


class ListPaymentEntries(Inputs):
    payment_type: Literal["Receive", "Pay", "Internal Transfer"] | None = None
    party_type: Literal["Customer", "Supplier"] | None = None
    party: Name | None = None
    state: Literal["draft", "submitted", "cancelled"] | None = None
    from_date: Day | None = None
    to_date: Day | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _rules(self) -> Self:
        in_order(self.from_date, self.to_date)
        if self.party is not None and self.party_type is None:
            raise ValueError("party needs party_type")
        return self


class GetPaymentEntry(Inputs):
    name: Name


async def list_bank_accounts(inputs: ListBankAccounts, context: Context) -> dict[str, Any]:
    # A party's bank account may carry the company too; only the company's own count.
    filters: list[list[Any]] = [
        ["company", "=", context.settings.company],
        ["is_company_account", "=", 1],
    ]
    if not inputs.include_disabled:
        filters.append(["disabled", "=", 0])
    rows = await context.erpnext.get_list(
        "Bank Account",
        fields=BANK_ACCOUNT_FIELDS,
        filters=filters,
        order_by="name asc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, BANK_ACCOUNT_FIELDS, flags={"is_default", "disabled"}) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def list_bank_transactions(inputs: ListBankTransactions, context: Context) -> dict[str, Any]:
    filters: list[list[Any]] = [
        ["company", "=", context.settings.company],
        *TRANSACTION_STATES[inputs.state],
    ]
    if inputs.bank_account is not None:
        filters.append(["bank_account", "=", inputs.bank_account])
    if inputs.from_date is not None:
        filters.append(["date", ">=", inputs.from_date.isoformat()])
    if inputs.to_date is not None:
        filters.append(["date", "<=", inputs.to_date.isoformat()])
    rows = await context.erpnext.get_list(
        "Bank Transaction",
        fields=TRANSACTION_FIELDS,
        filters=filters,
        order_by="date desc, name desc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, TRANSACTION_FIELDS, outside=TRANSACTION_OUTSIDE) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def get_bank_transaction(inputs: GetBankTransaction, context: Context) -> dict[str, Any]:
    doc = await get_named(
        context,
        "Bank Transaction",
        inputs.name,
        field="name",
        what="the bank transaction",
        company=True,
    )
    rows, cut = cut_rows(rows_of(doc, "payment_entries"))
    record = shape(doc, (*TRANSACTION_FIELDS, "modified"), outside=TRANSACTION_OUTSIDE)
    outside = record.pop("outside_text")
    name = str(doc.get("name", inputs.name))
    return cut_texts(
        {
            **record,
            "payment_entries": [shape(r, ALLOCATION_FIELDS) for r in rows],
            "url": form_url(context.settings.erpnext_public_url, "Bank Transaction", name),
            "truncated": ["payment_entries"] if cut else [],
            "outside_text": outside,
        }
    )


async def list_payment_entries(inputs: ListPaymentEntries, context: Context) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if inputs.payment_type is not None:
        filters.append(["payment_type", "=", inputs.payment_type])
    if inputs.party_type is not None:
        filters.append(["party_type", "=", inputs.party_type])
    if inputs.party is not None:
        filters.append(["party", "=", inputs.party])
    if inputs.state is not None:
        filters.append(["docstatus", "=", PAYMENT_STATES[inputs.state]])
    if inputs.from_date is not None:
        filters.append(["posting_date", ">=", inputs.from_date.isoformat()])
    if inputs.to_date is not None:
        filters.append(["posting_date", "<=", inputs.to_date.isoformat()])
    rows = await context.erpnext.get_list(
        "Payment Entry",
        fields=PAYMENT_FIELDS,
        filters=filters,
        order_by="posting_date desc, name desc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, PAYMENT_FIELDS, outside=PAYMENT_OUTSIDE) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def get_payment_entry(inputs: GetPaymentEntry, context: Context) -> dict[str, Any]:
    doc = await get_named(
        context, "Payment Entry", inputs.name, field="name", what="the payment entry", company=True
    )
    rows, cut = cut_rows(rows_of(doc, "references"))
    record = shape(doc, (*PAYMENT_FIELDS, *PAYMENT_DETAIL_FIELDS), outside=PAYMENT_OUTSIDE)
    outside = record.pop("outside_text")
    name = str(doc.get("name", inputs.name))
    return cut_texts(
        {
            **record,
            "references": [shape(r, REFERENCE_FIELDS) for r in rows],
            "url": form_url(context.settings.erpnext_public_url, "Payment Entry", name),
            "truncated": ["references"] if cut else [],
            "outside_text": outside,
        }
    )


OPERATIONS: list[Operation[Any]] = [
    Operation(
        name="list_bank_accounts",
        title="List bank accounts",
        description=(
            "List the assigned company's own bank accounts, ordered by ID; parties' bank "
            "accounts are left out, and so are disabled ones unless `include_disabled` is "
            "true. `account` is the ledger account the bank account books to. Use the IDs "
            "(`name`) as `bank_account` elsewhere."
        ),
        kind="read",
        inputs=ListBankAccounts,
        run=list_bank_accounts,
    ),
    Operation(
        name="list_bank_transactions",
        title="List bank transactions",
        description=(
            "List the assigned company's bank transactions (lines imported from bank "
            "statements), newest date first. `state`: unreconciled (the default: submitted, "
            "with an amount not yet allocated to vouchers), reconciled, pending (drafts, not "
            "yet offered for reconciliation) or all (every state except cancelled). Filter by "
            "`bank_account` and date (`from_date`, `to_date`, YYYY-MM-DD). `party` is the "
            "party set on the line, by hand or by ERPNext's party matching where the site "
            "turns it on."
        ),
        kind="read",
        inputs=ListBankTransactions,
        run=list_bank_transactions,
    ),
    Operation(
        name="get_bank_transaction",
        title="Get bank transaction",
        description=(
            "Get one bank transaction of the assigned company by its exact number (`name`), "
            "with the vouchers its amount is allocated to: `payment_document` names the "
            "DocType of each `payment_entry` (Payment Entry, Journal Entry, Sales Invoice, "
            "Purchase Invoice or Bank Transaction)."
        ),
        kind="read",
        inputs=GetBankTransaction,
        run=get_bank_transaction,
    ),
    Operation(
        name="list_payment_entries",
        title="List payment entries",
        description=(
            "List the assigned company's payment entries, newest posting date first. Filter "
            "by `payment_type`, `party_type` with `party`, `state` (draft, submitted, "
            "cancelled) and posting date (`from_date`, `to_date`, YYYY-MM-DD). "
            "`clearance_date` is empty until bank reconciliation matches the payment; "
            "`unallocated_amount` is the part not allocated to invoices."
        ),
        kind="read",
        inputs=ListPaymentEntries,
        run=list_payment_entries,
    ),
    Operation(
        name="get_payment_entry",
        title="Get payment entry",
        description=(
            "Get one payment entry of the assigned company by its exact number (`name`), with "
            "its accounts and the invoices and other documents it is allocated to."
        ),
        kind="read",
        inputs=GetPaymentEntry,
        run=get_payment_entry,
    ),
]
