"""Bank and cash: the company's bank accounts, bank transactions and payment entries
(REQ-007)."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from enterich.shapes import (
    DOCSTATUS,
    Day,
    Flag,
    Inputs,
    Limit,
    Name,
    Offset,
    cut_rows,
    decimal,
    form_url,
    in_order,
    page,
    rows_of,
    shape,
    today,
)
from enterich.tools import (
    Context,
    Operation,
    Refusal,
    Table,
    drafts,
    get_document,
    get_named,
    unknown_name,
)

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
PAYMENT_DRAFT_FIELDS = (
    "payment_type",
    "posting_date",
    "party_type",
    "party",
    "bank_account",
    "paid_from",
    "paid_to",
    "paid_amount",
    "received_amount",
    "paid_from_account_currency",
    "paid_to_account_currency",
    "reference_no",
    "reference_date",
    "total_allocated_amount",
    "unallocated_amount",
)
DRAFT_REFERENCE_FIELDS = (*REFERENCE_FIELDS, "outstanding_amount")
PAYMENT_MATCH = "party and bank reference (reference_no)"

# An amount of a payment in cents: ERPNext keeps an amount as given but rounds the totals to
# the currency's precision, so a third decimal place would leave a difference
Money = Annotated[Decimal, Field(gt=0, le=1_000_000_000, decimal_places=2)]
# The bank's reference for a payment, as on the statement: free text, not a name (ERPNext's
# Data field); surrounding whitespace would defeat the duplicate check
BankReference = Annotated[str, Field(min_length=1, max_length=140, pattern=r"^\S(.*\S)?$")]


@dataclass(frozen=True)
class Side:
    """A payment received from a customer or made to a supplier (REQ-007-PRS-F004)."""

    payment_type: str
    invoice: str  # the DocType of the invoices it is allocated to
    party_field: str  # the invoice's party field
    bank_field: str  # where the bank's ledger account goes
    party_account_field: str  # where the party's account goes
    hold: bool  # whether its invoices can be on hold


SIDES = {
    "Customer": Side("Receive", "Sales Invoice", "customer", "paid_to", "paid_from", hold=False),
    "Supplier": Side("Pay", "Purchase Invoice", "supplier", "paid_from", "paid_to", hold=True),
}


def _unset(field: str) -> dict[str, None]:
    """An account field with its currency and type empty: ERPNext reads them again, but
    only while they are empty."""
    return {field: None, f"{field}_account_currency": None, f"{field}_account_type": None}


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


class Allocation(Inputs):
    reference_name: Name
    allocated_amount: Money


Allocations = Annotated[list[Allocation], Field(max_length=20)]


class CreateDraftPaymentEntry(Inputs):
    party_type: Literal["Customer", "Supplier"]
    party: Name
    bank_account: Name
    paid_amount: Money
    reference_no: BankReference
    reference_date: Day | None = None
    posting_date: Day | None = None
    references: Allocations | None = None
    allow_duplicate: Flag = False


class UpdateDraftPaymentEntry(drafts.DraftUpdate):
    bank_account: Name | None = None
    paid_amount: Money | None = None
    reference_no: BankReference | None = None
    reference_date: Day | None = None
    posting_date: Day | None = None
    references: Allocations | None = None


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
    return await get_document(
        context,
        "Bank Transaction",
        inputs.name,
        what="the bank transaction",
        fields=(*TRANSACTION_FIELDS, "modified"),
        outside=TRANSACTION_OUTSIDE,
        tables={"payment_entries": Table(ALLOCATION_FIELDS)},
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
        filters.append(["docstatus", "=", DOCSTATUS[inputs.state]])
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
    return await get_document(
        context,
        "Payment Entry",
        inputs.name,
        what="the payment entry",
        fields=(*PAYMENT_FIELDS, *PAYMENT_DETAIL_FIELDS),
        outside=PAYMENT_OUTSIDE,
        tables={"references": Table(REFERENCE_FIELDS)},
    )


async def _bank_ledger(context: Context, name: str) -> str:
    """The ledger account of an enabled bank account of the company's own."""
    doc = await get_named(
        context, "Bank Account", name, field="bank_account", what="the bank account", company=True
    )
    if not doc.get("is_company_account"):
        raise Refusal(
            f"bank_account: {name} is a party's bank account; give one of the company's own, "
            "as list_bank_accounts returns them."
        )
    if doc.get("disabled"):
        raise Refusal(f"bank_account: {name} is disabled; give an enabled bank account.")
    return str(doc.get("account"))


async def _check_references(
    context: Context, side: Side, party: str, references: Sequence[Allocation], paid: Decimal
) -> None:
    """REQ-007-PRS-F005: each invoice once, submitted, the party's, not a return, open, and
    allocated at most its outstanding amount; the allocations at most the paid amount; no
    purchase invoice on hold."""
    allocated = sum((r.allocated_amount for r in references), Decimal(0))
    if allocated > paid:
        raise Refusal(
            f"references: the allocations ({drafts.plain(allocated)}) exceed the paid amount "
            f"({drafts.plain(paid)}); lower them, or give the amount actually paid."
        )
    if not references:
        return
    names = [r.reference_name for r in references]
    if twice := sorted({n for n in names if names.count(n) > 1}):
        raise Refusal(f"references: give each invoice once; {', '.join(twice)} is given twice.")
    rows = await context.erpnext.get_list(
        side.invoice,
        fields=(
            "name",
            side.party_field,
            "docstatus",
            "is_return",
            "outstanding_amount",
            *(("on_hold",) if side.hold else ()),
        ),
        filters=[["company", "=", context.settings.company], ["name", "in", names]],
        order_by="name asc",
        start=0,
        page_length=len(names),
    )
    found = {str(row.get("name")): row for row in rows}
    what = f"the {side.invoice.lower()}"
    for reference in references:
        name = reference.reference_name
        row = found.get(name)
        if row is None:
            raise unknown_name("references", what, name)
        state = drafts.DOCSTATUS.get(row.get("docstatus", 0), "a draft")
        if state != "submitted":
            raise Refusal(f"references: {name} is {state}; only submitted invoices are paid.")
        if row.get(side.party_field) != party:
            raise Refusal(
                f"references: {name} is {row.get(side.party_field)}'s invoice, not {party}'s."
            )
        if row.get("is_return"):
            raise Refusal(f"references: {name} is a return; it takes no payment.")
        if row.get("on_hold"):
            raise Refusal(
                f"references: {name} is on hold; a person releases it in ERPNext before it is paid."
            )
        outstanding = decimal(row.get("outstanding_amount"))
        if outstanding <= 0:
            raise Refusal(f"references: {name} has nothing outstanding; it is paid.")
        if reference.allocated_amount > outstanding:
            raise Refusal(
                f"references: {drafts.plain(reference.allocated_amount)} is allocated to "
                f"{name}, but only {drafts.plain(outstanding)} of it is outstanding."
            )


async def _same_reference(
    context: Context, party_type: str, party: str, reference_no: str, draft: str | None = None
) -> list[str]:
    """Draft and submitted payment entries of the assigned company with the party and the
    bank's reference (REQ-007-PRS-F006), other than `draft`; cancelled ones don't count."""
    filters: list[list[Any]] = [
        ["company", "=", context.settings.company],
        ["docstatus", "in", [0, 1]],
        ["party_type", "=", party_type],
        ["party", "=", party],
        ["reference_no", "=", reference_no],
    ]
    if draft is not None:
        filters.append(["name", "!=", draft])
    rows = await context.erpnext.get_list(
        "Payment Entry",
        fields=("name",),
        filters=filters,
        order_by="name asc",
        start=0,
        page_length=drafts.MAX_DUPLICATE_ROWS,
    )
    return sorted(str(row.get("name")) for row in rows)


def _allocations(side: Side, references: Sequence[Allocation]) -> list[dict[str, Any]]:
    return [
        {
            "reference_doctype": side.invoice,
            "reference_name": r.reference_name,
            "allocated_amount": r.allocated_amount,
        }
        for r in references
    ]


def _payment_warnings(saved: dict[str, Any]) -> list[str]:
    """REQ-007-PRS-F007."""
    warnings: list[str] = []
    unallocated = decimal(saved.get("unallocated_amount"))
    if rows_of(saved, "references") and unallocated > 0:
        warnings.append(
            f"{drafts.plain(unallocated)} of the paid amount isn't allocated to an invoice; "
            "ERPNext books it as an advance."
        )
    paid_from = saved.get("paid_from_account_currency")
    paid_to = saved.get("paid_to_account_currency")
    if paid_from and paid_to and paid_from != paid_to:
        bank, party = (
            (paid_to, paid_from)
            if saved.get("payment_type") == "Receive"
            else (
                paid_from,
                paid_to,
            )
        )
        warnings.append(
            f"The bank account is in {bank}, the party's account in {party}: the draft's "
            "received_amount equals paid_amount and its exchange rates may not match the "
            "accounts. Correct them before submitting."
        )
    return warnings


def _payment_result(context: Context, saved: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    """The draft as REQ-001's Results say."""
    name = str(saved.get("name"))
    record = shape(
        saved,
        ("name", "modified", "status", "docstatus", "company", *PAYMENT_DRAFT_FIELDS),
        outside=PAYMENT_OUTSIDE,
    )
    outside_text = record.pop("outside_text")
    references, cut = cut_rows(rows_of(saved, "references"))
    return {
        **record,
        "references": [shape(r, DRAFT_REFERENCE_FIELDS) for r in references],
        "url": form_url(context.settings.erpnext_public_url, "Payment Entry", name),
        "warnings": warnings,
        "truncated": ["references"] if cut else [],
        "outside_text": outside_text,
    }


async def create_draft_payment_entry(
    inputs: CreateDraftPaymentEntry, context: Context
) -> dict[str, Any]:
    side = SIDES[inputs.party_type]
    ledger = await _bank_ledger(context, inputs.bank_account)
    await _check_references(
        context, side, inputs.party, inputs.references or [], inputs.paid_amount
    )
    matches = await _same_reference(context, inputs.party_type, inputs.party, inputs.reference_no)
    if matches and not inputs.allow_duplicate:
        raise drafts.refuse_duplicates(matches, PAYMENT_MATCH, "payment entry")
    posting_date = inputs.posting_date or today(context.settings.timezone)
    doc: dict[str, Any] = {
        "payment_type": side.payment_type,
        "party_type": inputs.party_type,
        "party": inputs.party,
        "bank_account": inputs.bank_account,
        side.bank_field: ledger,
        # One currency on both sides: ERPNext wants both amounts before it counts them.
        "paid_amount": inputs.paid_amount,
        "received_amount": inputs.paid_amount,
        "reference_no": inputs.reference_no,
        "reference_date": (inputs.reference_date or posting_date).isoformat(),
        "posting_date": posting_date.isoformat(),
    }
    if inputs.references is not None:
        doc["references"] = _allocations(side, inputs.references)
    saved = await drafts.insert(context, "Payment Entry", doc)
    warnings = (
        [drafts.duplicate_warning(matches, PAYMENT_MATCH, "payment entry")] if matches else []
    )
    return _payment_result(context, saved, warnings + _payment_warnings(saved))


async def update_draft_payment_entry(
    inputs: UpdateDraftPaymentEntry, context: Context
) -> dict[str, Any]:
    # Enterich changes only the payments it creates.
    stored = await drafts.editable(
        context,
        "Payment Entry",
        inputs.name,
        inputs.modified,
        "the payment entry",
        only=[
            {"payment_type": side.payment_type, "party_type": party_type}
            for party_type, side in SIDES.items()
        ],
    )
    party_type, party = str(stored.get("party_type")), str(stored.get("party"))
    side = SIDES[party_type]
    doc: dict[str, Any] = {}
    if inputs.bank_account is not None:
        doc["bank_account"] = inputs.bank_account
        doc |= _unset(side.bank_field)
        doc[side.bank_field] = await _bank_ledger(context, inputs.bank_account)
    paid = inputs.paid_amount or decimal(stored.get("paid_amount"))
    if inputs.references is not None:
        await _check_references(context, side, party, inputs.references, paid)
        doc["references"] = _allocations(side, inputs.references)
        # ERPNext sets the party's account again for the references: with advances booked
        # apart, the advance account without invoices, the party's own with them.
        doc |= _unset(side.party_account_field)
    elif inputs.paid_amount is not None:
        allocated = sum(
            (decimal(r.get("allocated_amount")) for r in rows_of(stored, "references")),
            Decimal(0),
        )
        if allocated > inputs.paid_amount:
            raise Refusal(
                f"paid_amount: {drafts.plain(inputs.paid_amount)} is less than the "
                f"{drafts.plain(allocated)} the draft allocates to invoices; give the "
                "references too."
            )
    if inputs.paid_amount is not None:
        doc |= {"paid_amount": inputs.paid_amount, "received_amount": inputs.paid_amount}
    for field in ("reference_no", "reference_date", "posting_date"):
        value = getattr(inputs, field)
        if value is not None:
            doc[field] = value if isinstance(value, str) else value.isoformat()
    matches: list[str] = []
    if inputs.reference_no is not None:
        matches = await _same_reference(
            context, party_type, party, inputs.reference_no, draft=inputs.name
        )
    saved = await drafts.save_update(
        context, "Payment Entry", inputs.name, {**doc, "modified": inputs.modified}
    )
    warnings = (
        [drafts.duplicate_warning(matches, PAYMENT_MATCH, "payment entry")] if matches else []
    )
    return _payment_result(context, saved, warnings + _payment_warnings(saved))


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
    Operation(
        name="create_draft_payment_entry",
        title="Create draft payment entry",
        description=(
            "Create a draft payment entry of the assigned company for a payment received from "
            "a customer (`party_type` Customer) or made to a supplier (Supplier) through one of "
            "the company's bank accounts (`bank_account`, from `list_bank_accounts`); a person "
            "reviews and submits it in ERPNext. Give `paid_amount` and the bank's reference "
            "(`reference_no`) as on the statement; `posting_date` defaults to today, "
            "`reference_date` to the posting date. Allocate the payment to the party's "
            "submitted, open invoices with `references`, each at most its outstanding amount "
            "and together at most `paid_amount`; what isn't allocated becomes an advance, "
            "named in `warnings`. The bank account and the party's account must be in one "
            "currency. A `reference_no` already recorded for the party, in a draft or a "
            "submitted payment entry, is refused unless `allow_duplicate` is true. After an "
            "error or a timeout, list the drafts (`list_payment_entries` with `state` draft) "
            "before creating again: the first may have been saved."
        ),
        kind="create",
        inputs=CreateDraftPaymentEntry,
        run=create_draft_payment_entry,
        doctype="Payment Entry",
    ),
    Operation(
        name="update_draft_payment_entry",
        title="Update draft payment entry",
        description=(
            "Change a draft payment entry of the assigned company that the agent user created. "
            "Give its `name` and its `modified` as last read; a draft changed since is refused. "
            "Give only what changes: `references` replace all allocations, and an empty list "
            "removes them. A new `posting_date` leaves `reference_date` as it is. The party "
            "stays; for another party, create a new draft."
        ),
        kind="update",
        inputs=UpdateDraftPaymentEntry,
        run=update_draft_payment_entry,
        doctype="Payment Entry",
    ),
]
