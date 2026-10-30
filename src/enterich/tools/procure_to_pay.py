"""Procure to pay: suppliers, purchase invoices, purchase tax templates, payables (REQ-005)."""

from typing import Annotated, Any, Literal, Self

from pydantic import Field, model_validator

from enterich.shapes import (
    Day,
    Flag,
    Inputs,
    InvoiceState,
    Limit,
    Name,
    Offset,
    Quantity,
    Rate,
    Remarks,
    Search,
    in_order,
    today,
)
from enterich.tools import Context, Operation, drafts, get_named, invoicing
from enterich.tools.invoicing import AgeingBasedOn

PURCHASE = invoicing.Side(
    party="Supplier",
    party_field="supplier",
    party_fields=(
        "name",
        "supplier_name",
        "supplier_type",
        "supplier_group",
        "tax_id",
        "default_currency",
        "disabled",
    ),
    party_outside=frozenset({"supplier_name", "tax_id"}),
    invoice="Purchase Invoice",
    invoice_fields=(
        "name",
        "supplier",
        "supplier_name",
        "bill_no",
        "bill_date",
        "posting_date",
        "due_date",
        "currency",
        "net_total",
        "grand_total",
        "outstanding_amount",
        "status",
        "docstatus",
        "is_return",
        "owner",
        "modified",
    ),
    invoice_outside=frozenset({"supplier_name", "bill_no", "remarks"}),
    item_fields=(
        "item_code",
        "item_name",
        "description",
        "qty",
        "uom",
        "rate",
        "amount",
        "expense_account",
        "item_tax_template",
        "cost_center",
    ),
    item_outside=frozenset({"item_name", "description"}),
    tax_fields=(
        "charge_type",
        "account_head",
        "add_deduct_tax",
        "rate",
        "tax_amount",
        "description",
    ),
    template="Purchase Taxes and Charges Template",
    report="Accounts Payable",
    aged_fields=(
        "party",
        "voucher_type",
        "voucher_no",
        "bill_no",
        "bill_date",
        "posting_date",
        "due_date",
        "invoiced",
        "paid",
        "credit_note",
        "outstanding",
        "currency",
        "age",
    ),
    aged_outside=frozenset({"bill_no"}),
)
DRAFT_FIELDS = (
    "supplier",
    "posting_date",
    "due_date",
    "currency",
    "net_total",
    "total_taxes_and_charges",
    "grand_total",
)
DRAFT_ROW_FIELDS = ("item_code", "qty", "rate", "amount", "expense_account", "is_free_item")
DRAFT_MATCH = "supplier, posting date and items"
BILL_MATCH = "supplier and bill_no"

# The supplier's invoice number as printed: free text, not a name (ERPNext's Data field);
# surrounding whitespace would defeat the duplicate check
BillNo = Annotated[str, Field(min_length=1, max_length=140, pattern=r"^\S(.*\S)?$")]


class ListSuppliers(Inputs):
    search: Search | None = None
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class GetSupplier(Inputs):
    name: Name


class ListPurchaseInvoices(Inputs):
    supplier: Name | None = None
    state: InvoiceState | None = None
    from_date: Day | None = None
    to_date: Day | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _period(self) -> Self:
        in_order(self.from_date, self.to_date)
        return self


class GetPurchaseInvoice(Inputs):
    name: Name


class ListPurchaseTaxTemplates(Inputs):
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class ReportAccountsPayable(Inputs):
    as_of_date: Day | None = None
    supplier: Name | None = None
    ageing_based_on: AgeingBasedOn = "due_date"
    limit: Limit = 20
    offset: Offset = 0


class PurchaseInvoiceItem(Inputs):
    item_code: Name
    qty: Quantity
    rate: Rate
    uom: Name | None = None
    expense_account: Name | None = None
    cost_center: Name | None = None


PurchaseInvoiceItems = Annotated[list[PurchaseInvoiceItem], Field(min_length=1, max_length=20)]


class CreateDraftPurchaseInvoice(Inputs):
    supplier: Name
    bill_no: BillNo | None = None
    bill_date: Day | None = None
    posting_date: Day | None = None
    due_date: Day | None = None
    items: PurchaseInvoiceItems
    taxes_and_charges: Name | None = None
    remarks: Remarks | None = None
    allow_duplicate: Flag = False


class UpdateDraftPurchaseInvoice(drafts.DraftUpdate):
    bill_no: BillNo | Literal[""] | None = None
    bill_date: Day | None = None
    posting_date: Day | None = None
    due_date: Day | None = None
    items: PurchaseInvoiceItems | None = None
    taxes_and_charges: Name | Literal[""] | None = None
    remarks: Remarks | None = None


async def list_suppliers(inputs: ListSuppliers, context: Context) -> dict[str, Any]:
    return await invoicing.list_parties(
        PURCHASE,
        context,
        search=inputs.search,
        include_disabled=inputs.include_disabled,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def get_supplier(inputs: GetSupplier, context: Context) -> dict[str, Any]:
    return await invoicing.get_party(PURCHASE, context, inputs.name)


async def list_purchase_invoices(inputs: ListPurchaseInvoices, context: Context) -> dict[str, Any]:
    return await invoicing.list_invoices(
        PURCHASE,
        context,
        party=inputs.supplier,
        state=inputs.state,
        from_date=inputs.from_date,
        to_date=inputs.to_date,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def get_purchase_invoice(inputs: GetPurchaseInvoice, context: Context) -> dict[str, Any]:
    return await invoicing.get_invoice(PURCHASE, context, inputs.name)


async def list_purchase_tax_templates(
    inputs: ListPurchaseTaxTemplates, context: Context
) -> dict[str, Any]:
    return await invoicing.list_templates(
        PURCHASE,
        context,
        include_disabled=inputs.include_disabled,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def report_accounts_payable(
    inputs: ReportAccountsPayable, context: Context
) -> dict[str, Any]:
    return await invoicing.aged_report(
        PURCHASE,
        context,
        as_of_date=inputs.as_of_date,
        party=inputs.supplier,
        ageing_based_on=inputs.ageing_based_on,
        limit=inputs.limit,
        offset=inputs.offset,
    )


def _invoice_body(
    inputs: CreateDraftPurchaseInvoice | UpdateDraftPurchaseInvoice,
    taxes: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """The catalogue's "Sent to ERPNext" for the given inputs; the supplier and
    `update_stock` 0 only on create: ERPNext would keep the first supplier's address,
    terms and accounts."""
    doc: dict[str, Any] = {}
    if isinstance(inputs, CreateDraftPurchaseInvoice):
        doc["supplier"] = inputs.supplier
    if inputs.bill_no is not None:
        doc["bill_no"] = inputs.bill_no
    if inputs.bill_date is not None:
        doc["bill_date"] = inputs.bill_date.isoformat()
    if inputs.posting_date is not None:
        doc |= {"posting_date": inputs.posting_date.isoformat(), "set_posting_time": 1}
    if inputs.due_date is not None:
        doc["due_date"] = inputs.due_date.isoformat()
    if inputs.items is not None:
        doc["items"] = [row.model_dump(exclude_none=True) for row in inputs.items]
    if inputs.taxes_and_charges is not None:
        doc |= {"taxes_and_charges": inputs.taxes_and_charges, "taxes": taxes or []}
    if inputs.remarks is not None:
        doc["remarks"] = inputs.remarks
    if isinstance(inputs, CreateDraftPurchaseInvoice):
        doc["update_stock"] = 0
    return doc


async def _same_bill(
    context: Context, supplier: str, bill_no: str, draft: str | None = None
) -> list[str]:
    """Draft and submitted invoices of the assigned company with the supplier's invoice
    number (REQ-005-PRS-F006), other than `draft`; cancelled ones don't count."""
    filters: list[list[Any]] = [
        ["company", "=", context.settings.company],
        ["docstatus", "in", [0, 1]],
        ["supplier", "=", supplier],
        ["bill_no", "=", bill_no],
    ]
    if draft is not None:
        filters.append(["name", "!=", draft])
    rows = await context.erpnext.get_list(
        "Purchase Invoice",
        fields=("name",),
        filters=filters,
        order_by="name asc",
        start=0,
        page_length=drafts.MAX_DUPLICATE_ROWS,
    )
    return sorted(str(row.get("name")) for row in rows)


async def create_draft_purchase_invoice(
    inputs: CreateDraftPurchaseInvoice, context: Context
) -> dict[str, Any]:
    party = await get_named(
        context, "Supplier", inputs.supplier, field="supplier", what="the supplier"
    )
    taxes = None
    if inputs.taxes_and_charges is not None:
        taxes = await drafts.tax_rows(context, PURCHASE.template, inputs.taxes_and_charges)
    doc = drafts.due_dates(_invoice_body(inputs, taxes))
    # As the form does for a new invoice: ERPNext withholds only with apply_tds set.
    if party.get("tax_withholding_category") or party.get("tax_withholding_group"):
        doc["apply_tds"] = 1
    if inputs.bill_no is not None:
        match, kind = BILL_MATCH, "purchase invoice"
        matches = await _same_bill(context, inputs.supplier, inputs.bill_no)
    else:
        match, kind = DRAFT_MATCH, "draft"
        posting_date = inputs.posting_date or today(context.settings.timezone)
        matches = await drafts.duplicates(
            context,
            "Purchase Invoice",
            [["supplier", "=", inputs.supplier], ["posting_date", "=", posting_date.isoformat()]],
            doc["items"],
        )
    if matches and not inputs.allow_duplicate:
        raise drafts.refuse_duplicates(matches, match, kind)
    saved = await context.erpnext.insert(
        "Purchase Invoice", {**doc, "company": context.settings.company, "docstatus": 0}
    )
    warnings = [drafts.duplicate_warning(matches, match, kind)] if matches else []
    warnings += drafts.tax_warning(saved, inputs.taxes_and_charges)
    warnings += drafts.row_warnings(saved, doc["items"], account="expense_account")
    return await drafts.result(
        context, "Purchase Invoice", saved, DRAFT_FIELDS, warnings, DRAFT_ROW_FIELDS
    )


async def update_draft_purchase_invoice(
    inputs: UpdateDraftPurchaseInvoice, context: Context
) -> dict[str, Any]:
    stored = await drafts.editable(
        context, "Purchase Invoice", inputs.name, inputs.modified, "the purchase invoice"
    )
    taxes = None
    if inputs.taxes_and_charges:
        taxes = await drafts.tax_rows(context, PURCHASE.template, inputs.taxes_and_charges)
    day = today(context.settings.timezone)
    doc = drafts.due_dates(_invoice_body(inputs, taxes), stored, day)
    matches: list[str] = []
    if inputs.bill_no:
        supplier = str(stored.get("supplier"))
        matches = await _same_bill(context, supplier, inputs.bill_no, draft=inputs.name)
    saved = await drafts.save_update(
        context, "Purchase Invoice", inputs.name, {**doc, "modified": inputs.modified}
    )
    warnings = (
        [drafts.duplicate_warning(matches, BILL_MATCH, "purchase invoice")] if matches else []
    )
    warnings += drafts.tax_warning(saved, inputs.taxes_and_charges)
    warnings += drafts.row_warnings(saved, doc.get("items"), account="expense_account")
    return await drafts.result(
        context, "Purchase Invoice", saved, DRAFT_FIELDS, warnings, DRAFT_ROW_FIELDS
    )


OPERATIONS: list[Operation[Any]] = [
    Operation(
        name="list_suppliers",
        title="List suppliers",
        description=(
            "List suppliers, ordered by ID. `search` matches part of the ID or the supplier "
            "name. Disabled suppliers are left out unless `include_disabled` is true. Use the "
            "IDs (`name`) as `supplier` elsewhere; `has_more` says whether `offset` can fetch "
            "more."
        ),
        kind="read",
        inputs=ListSuppliers,
        run=list_suppliers,
    ),
    Operation(
        name="get_supplier",
        title="Get supplier",
        description=(
            "Get one supplier by its exact ID (`name`), with its payment terms and the "
            "addresses linked to it."
        ),
        kind="read",
        inputs=GetSupplier,
        run=get_supplier,
    ),
    Operation(
        name="list_purchase_invoices",
        title="List purchase invoices",
        description=(
            "List the assigned company's purchase invoices, newest posting date first, with "
            "the supplier's invoice number (`bill_no`) and date. Filter by `supplier` (ID), "
            "`state` and posting date (`from_date`, `to_date`, YYYY-MM-DD). States: draft, "
            "unpaid (includes overdue), overdue (due before today), paid, return, cancelled."
        ),
        kind="read",
        inputs=ListPurchaseInvoices,
        run=list_purchase_invoices,
    ),
    Operation(
        name="get_purchase_invoice",
        title="Get purchase invoice",
        description=(
            "Get one purchase invoice of the assigned company by its exact number (`name`), "
            "with its item and tax rows."
        ),
        kind="read",
        inputs=GetPurchaseInvoice,
        run=get_purchase_invoice,
    ),
    Operation(
        name="list_purchase_tax_templates",
        title="List purchase tax templates",
        description=(
            "List the assigned company's purchase tax templates, ordered by name. Disabled "
            "ones are left out unless `include_disabled` is true."
        ),
        kind="read",
        inputs=ListPurchaseTaxTemplates,
        run=list_purchase_tax_templates,
    ),
    Operation(
        name="report_accounts_payable",
        title="Accounts payable",
        description=(
            "What the assigned company owes its suppliers as of `as_of_date` (default today), "
            "one record per open voucher with the supplier's invoice number (`bill_no`) and "
            "date, aged by due date or posting date: `range0` not yet due, then `range1` to "
            "`range5` for 0-30, 31-60, 61-90, 91-120 and over 120 days. `total_outstanding` "
            "covers every record, not only this page. Supplier names aren't in the records; "
            "`get_supplier` gives them."
        ),
        kind="read",
        inputs=ReportAccountsPayable,
        run=report_accounts_payable,
    ),
    Operation(
        name="create_draft_purchase_invoice",
        title="Create draft purchase invoice",
        description=(
            "Create a draft purchase invoice of the assigned company from a supplier's "
            "invoice; a person reviews and submits it in ERPNext. Give `bill_no` and "
            "`bill_date` as printed on the supplier's invoice, and each item's `rate` from it. "
            "The draft never updates stock. `posting_date` defaults to today, `due_date` to "
            "the supplier's payment terms, counted from `bill_date` when given; for a bill older "
            "than its terms, ERPNext refuses its own count, so give the bill's `due_date`. "
            "A `bill_no` "
            "already recorded for the supplier, in a draft or a submitted invoice, is refused "
            "unless `allow_duplicate` is true; without `bill_no`, a draft with the same "
            "supplier, posting date and items is. A rate a pricing rule replaced, and an "
            "`expense_account` ERPNext replaced, are named in `warnings`. After an error or a "
            "timeout, list the drafts (`list_purchase_invoices` with `state` draft) before "
            "creating again: the first may have been saved."
        ),
        kind="create",
        inputs=CreateDraftPurchaseInvoice,
        run=create_draft_purchase_invoice,
    ),
    Operation(
        name="update_draft_purchase_invoice",
        title="Update draft purchase invoice",
        description=(
            "Change a draft purchase invoice of the assigned company. Give its `name` and its "
            "`modified` as last read; a draft changed since is refused. Give only what "
            "changes: `items` replace all rows; an empty `bill_no`, `remarks` or "
            "`taxes_and_charges` clears it, and a cleared tax template takes its tax rows "
            "with it. The supplier stays; for another supplier, create a new draft."
        ),
        kind="update",
        inputs=UpdateDraftPurchaseInvoice,
        run=update_draft_purchase_invoice,
    ),
]
