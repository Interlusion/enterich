"""Order to cash: customers, sales invoices, sales tax templates, receivables (REQ-004)."""

from decimal import Decimal
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, model_validator

from erpel.shapes import (
    Day,
    Flag,
    Inputs,
    InvoiceState,
    Limit,
    Modified,
    Name,
    Offset,
    Quantity,
    Rate,
    Remarks,
    Search,
    cut_rows,
    cut_texts,
    decimal,
    form_url,
    in_order,
    invoice_state,
    like_pattern,
    page,
    rows_of,
    shape,
    today,
)
from erpel.tools import Context, Operation, Refusal, drafts, get_named

CUSTOMER_FIELDS = (
    "name",
    "customer_name",
    "customer_type",
    "customer_group",
    "tax_id",
    "default_currency",
    "disabled",
)
CUSTOMER_OUTSIDE = {"customer_name", "tax_id"}
ADDRESS_FIELDS = (
    "name",
    "address_type",
    "is_primary_address",
    "address_line1",
    "address_line2",
    "city",
    "pincode",
    "country",
)
ADDRESS_OUTSIDE = {"address_line1", "address_line2", "city", "pincode"}
INVOICE_FIELDS = (
    "name",
    "customer",
    "customer_name",
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
)
INVOICE_DETAIL_FIELDS = (
    "taxes_and_charges",
    "total_taxes_and_charges",
    "return_against",
    "remarks",
)
INVOICE_OUTSIDE = {"customer_name", "remarks"}
INVOICE_ITEM_FIELDS = (
    "item_code",
    "item_name",
    "description",
    "qty",
    "uom",
    "rate",
    "amount",
    "income_account",
    "item_tax_template",
    "cost_center",
)
INVOICE_ITEM_OUTSIDE = {"item_name", "description"}
TAX_FIELDS = ("charge_type", "account_head", "rate", "tax_amount", "description")
TEMPLATE_FIELDS = ("name", "title", "is_default", "tax_category", "disabled")
RECEIVABLE_FIELDS = (
    "party",
    "voucher_type",
    "voucher_no",
    "posting_date",
    "due_date",
    "invoiced",
    "paid",
    "credit_note",
    "outstanding",
    "currency",
    "age",
)
SALES_TEMPLATE = "Sales Taxes and Charges Template"
DRAFT_FIELDS = (
    "customer",
    "posting_date",
    "due_date",
    "currency",
    "net_total",
    "total_taxes_and_charges",
    "grand_total",
)
DRAFT_MATCH = "customer, posting date and items"
AGEING = tuple(f"range{i}" for i in range(6))  # range0: not yet due; then ERPNext's 30, 60, 90, 120
AGEING_BASED_ON = {"due_date": "Due Date", "posting_date": "Posting Date"}
MAX_ADDRESSES = 100


class ListCustomers(Inputs):
    search: Search | None = None
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class GetCustomer(Inputs):
    name: Name


class ListSalesInvoices(Inputs):
    customer: Name | None = None
    state: InvoiceState | None = None
    from_date: Day | None = None
    to_date: Day | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _period(self) -> Self:
        in_order(self.from_date, self.to_date)
        return self


class GetSalesInvoice(Inputs):
    name: Name


class ListSalesTaxTemplates(Inputs):
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class ReportAccountsReceivable(Inputs):
    as_of_date: Day | None = None
    customer: Name | None = None
    ageing_based_on: Literal["due_date", "posting_date"] = "due_date"
    limit: Limit = 20
    offset: Offset = 0


class SalesInvoiceItem(Inputs):
    item_code: Name
    qty: Quantity
    rate: Rate | None = None
    uom: Name | None = None
    income_account: Name | None = None
    cost_center: Name | None = None


SalesInvoiceItems = Annotated[list[SalesInvoiceItem], Field(min_length=1, max_length=20)]


class CreateDraftSalesInvoice(Inputs):
    customer: Name
    posting_date: Day | None = None
    due_date: Day | None = None
    items: SalesInvoiceItems
    taxes_and_charges: Name | None = None
    remarks: Remarks | None = None
    allow_duplicate: Flag = False


class UpdateDraftSalesInvoice(Inputs):
    name: Name
    modified: Modified
    posting_date: Day | None = None
    due_date: Day | None = None
    items: SalesInvoiceItems | None = None
    taxes_and_charges: Name | Literal[""] | None = None
    remarks: Remarks | None = None

    @model_validator(mode="after")
    def _changes(self) -> Self:
        given = self.model_dump(exclude={"name", "modified"}, exclude_none=True)
        if not given:
            raise ValueError(
                "give at least one of posting_date, due_date, items, taxes_and_charges, remarks"
            )
        return self


def _customer(doc: dict[str, Any]) -> dict[str, Any]:
    return shape(doc, CUSTOMER_FIELDS, outside=CUSTOMER_OUTSIDE, flags={"disabled"})


def _invoice(doc: dict[str, Any]) -> dict[str, Any]:
    return shape(doc, INVOICE_FIELDS, outside=INVOICE_OUTSIDE, flags={"is_return"})


async def list_customers(inputs: ListCustomers, context: Context) -> dict[str, Any]:
    or_filters: list[list[Any]] = []
    if inputs.search is not None:
        pattern = like_pattern(inputs.search)
        or_filters = [["name", "like", pattern], ["customer_name", "like", pattern]]
    rows = await context.erpnext.get_list(
        "Customer",
        fields=CUSTOMER_FIELDS,
        filters=[] if inputs.include_disabled else [["disabled", "=", 0]],
        or_filters=or_filters,
        order_by="name asc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    return page([_customer(row) for row in rows], inputs.offset, inputs.limit)


async def get_customer(inputs: GetCustomer, context: Context) -> dict[str, Any]:
    doc = await get_named(context, "Customer", inputs.name, field="name", what="the customer")
    name = str(doc.get("name", inputs.name))
    addresses = await context.erpnext.get_list(
        "Address",
        fields=ADDRESS_FIELDS,
        filters=[
            ["Dynamic Link", "link_doctype", "=", "Customer"],
            ["Dynamic Link", "link_name", "=", name],
        ],
        order_by="name asc",
        start=0,
        page_length=MAX_ADDRESSES + 1,
    )
    record = shape(
        doc, (*CUSTOMER_FIELDS, "payment_terms"), outside=CUSTOMER_OUTSIDE, flags={"disabled"}
    )
    outside = record.pop("outside_text")
    return cut_texts(
        {
            **record,
            "addresses": [
                shape(a, ADDRESS_FIELDS, outside=ADDRESS_OUTSIDE, flags={"is_primary_address"})
                for a in addresses[:MAX_ADDRESSES]
            ],
            "modified": doc.get("modified"),
            "url": form_url(context.settings.erpnext_public_url, "Customer", name),
            "truncated": ["addresses"] if len(addresses) > MAX_ADDRESSES else [],
            "outside_text": outside,
        }
    )


async def list_sales_invoices(inputs: ListSalesInvoices, context: Context) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if inputs.customer is not None:
        filters.append(["customer", "=", inputs.customer])
    if inputs.state is not None:
        filters += invoice_state(inputs.state, today(context.settings.timezone))
    if inputs.from_date is not None:
        filters.append(["posting_date", ">=", inputs.from_date.isoformat()])
    if inputs.to_date is not None:
        filters.append(["posting_date", "<=", inputs.to_date.isoformat()])
    rows = await context.erpnext.get_list(
        "Sales Invoice",
        fields=INVOICE_FIELDS,
        filters=filters,
        order_by="posting_date desc, name desc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    return page([_invoice(row) for row in rows], inputs.offset, inputs.limit)


async def get_sales_invoice(inputs: GetSalesInvoice, context: Context) -> dict[str, Any]:
    doc = await get_named(
        context, "Sales Invoice", inputs.name, field="name", what="the sales invoice", company=True
    )
    items, items_cut = cut_rows(rows_of(doc, "items"))
    taxes, taxes_cut = cut_rows(rows_of(doc, "taxes"))
    record = shape(
        doc, (*INVOICE_FIELDS, *INVOICE_DETAIL_FIELDS), outside=INVOICE_OUTSIDE, flags={"is_return"}
    )
    outside = record.pop("outside_text")
    return cut_texts(
        {
            **record,
            "items": [shape(r, INVOICE_ITEM_FIELDS, outside=INVOICE_ITEM_OUTSIDE) for r in items],
            "taxes": [shape(r, TAX_FIELDS) for r in taxes],
            "url": form_url(
                context.settings.erpnext_public_url,
                "Sales Invoice",
                str(doc.get("name", inputs.name)),
            ),
            "truncated": [t for t, cut in (("items", items_cut), ("taxes", taxes_cut)) if cut],
            "outside_text": outside,
        }
    )


async def list_sales_tax_templates(
    inputs: ListSalesTaxTemplates, context: Context
) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if not inputs.include_disabled:
        filters.append(["disabled", "=", 0])
    rows = await context.erpnext.get_list(
        "Sales Taxes and Charges Template",
        fields=TEMPLATE_FIELDS,
        filters=filters,
        order_by="name asc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, TEMPLATE_FIELDS, flags={"is_default", "disabled"}) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def report_accounts_receivable(
    inputs: ReportAccountsReceivable, context: Context
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "company": context.settings.company,
        "report_date": (inputs.as_of_date or today(context.settings.timezone)).isoformat(),
        "party_type": "Customer",
        "ageing_based_on": AGEING_BASED_ON[inputs.ageing_based_on],
        "age_as_on": "Report Date",
        "range": "30, 60, 90, 120",
    }
    if inputs.customer is not None:
        filters["party"] = [inputs.customer]
    answer = await context.erpnext.run_report("Accounts Receivable", filters)
    if answer.get("prepared_report"):
        raise Refusal(
            "ERPNext runs Accounts Receivable as a prepared report, and Erpel doesn't wait for "
            "one; the operator can turn that off (see Erpel's configuration guide)."
        )
    # ERPNext appends its total row as a list; the rows themselves are objects.
    listed = cast("list[Any]", answer["result"])
    rows = [cast("dict[str, Any]", row) for row in listed if isinstance(row, dict)]
    total: Decimal = sum((decimal(row.get("outstanding")) for row in rows), Decimal(0))
    shown = rows[inputs.offset : inputs.offset + inputs.limit + 1]
    records = [
        {
            **{f: row.get(f) for f in RECEIVABLE_FIELDS},
            "ageing": {r: row.get(r) for r in AGEING},
            "outside_text": {},
        }
        for row in shown
    ]
    return {**page(records, inputs.offset, inputs.limit), "total_outstanding": total}


def _invoice_body(
    inputs: CreateDraftSalesInvoice | UpdateDraftSalesInvoice, taxes: list[dict[str, Any]] | None
) -> dict[str, Any]:
    """The catalogue's "Sent to ERPNext" for the given inputs; the customer only on create:
    ERPNext would keep the first customer's address, terms and accounts."""
    doc: dict[str, Any] = {}
    if isinstance(inputs, CreateDraftSalesInvoice):
        doc["customer"] = inputs.customer
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
    return doc


async def create_draft_sales_invoice(
    inputs: CreateDraftSalesInvoice, context: Context
) -> dict[str, Any]:
    taxes = None
    if inputs.taxes_and_charges is not None:
        taxes = await drafts.tax_rows(context, SALES_TEMPLATE, inputs.taxes_and_charges)
    doc = _invoice_body(inputs, taxes)
    posting_date = inputs.posting_date or today(context.settings.timezone)
    matches = await drafts.duplicates(
        context,
        "Sales Invoice",
        [["customer", "=", inputs.customer], ["posting_date", "=", posting_date.isoformat()]],
        doc["items"],
    )
    if matches and not inputs.allow_duplicate:
        raise drafts.refuse_duplicates(matches, DRAFT_MATCH)
    saved = await context.erpnext.insert(
        "Sales Invoice", {**doc, "company": context.settings.company, "docstatus": 0}
    )
    warnings = [drafts.duplicate_warning(matches, DRAFT_MATCH)] if matches else []
    warnings += drafts.tax_warning(saved, inputs.taxes_and_charges)
    warnings += drafts.rate_warnings(saved, doc["items"])
    return await drafts.result(context, "Sales Invoice", saved, DRAFT_FIELDS, warnings)


async def update_draft_sales_invoice(
    inputs: UpdateDraftSalesInvoice, context: Context
) -> dict[str, Any]:
    await drafts.editable(
        context, "Sales Invoice", inputs.name, inputs.modified, "the sales invoice"
    )
    taxes = None
    if inputs.taxes_and_charges:
        taxes = await drafts.tax_rows(context, SALES_TEMPLATE, inputs.taxes_and_charges)
    doc = _invoice_body(inputs, taxes)
    saved = await drafts.save_update(
        context, "Sales Invoice", inputs.name, {**doc, "modified": inputs.modified}
    )
    warnings = drafts.tax_warning(saved, inputs.taxes_and_charges)
    warnings += drafts.rate_warnings(saved, doc.get("items"))
    return await drafts.result(context, "Sales Invoice", saved, DRAFT_FIELDS, warnings)


OPERATIONS: list[Operation[Any]] = [
    Operation(
        name="list_customers",
        title="List customers",
        description=(
            "List customers, ordered by ID. `search` matches part of the ID or the customer "
            "name. Disabled customers are left out unless `include_disabled` is true. Use the "
            "IDs (`name`) as `customer` elsewhere; `has_more` says whether `offset` can fetch "
            "more."
        ),
        kind="read",
        inputs=ListCustomers,
        run=list_customers,
    ),
    Operation(
        name="get_customer",
        title="Get customer",
        description=(
            "Get one customer by its exact ID (`name`), with its payment terms and the "
            "addresses linked to it."
        ),
        kind="read",
        inputs=GetCustomer,
        run=get_customer,
    ),
    Operation(
        name="list_sales_invoices",
        title="List sales invoices",
        description=(
            "List the assigned company's sales invoices, newest posting date first. Filter by "
            "`customer` (ID), `state` and posting date (`from_date`, `to_date`, YYYY-MM-DD). "
            "States: draft, unpaid (includes overdue), overdue (due before today), paid, "
            "return, cancelled."
        ),
        kind="read",
        inputs=ListSalesInvoices,
        run=list_sales_invoices,
    ),
    Operation(
        name="get_sales_invoice",
        title="Get sales invoice",
        description=(
            "Get one sales invoice of the assigned company by its exact number (`name`), with "
            "its item and tax rows."
        ),
        kind="read",
        inputs=GetSalesInvoice,
        run=get_sales_invoice,
    ),
    Operation(
        name="list_sales_tax_templates",
        title="List sales tax templates",
        description=(
            "List the assigned company's sales tax templates, ordered by name. Disabled ones "
            "are left out unless `include_disabled` is true."
        ),
        kind="read",
        inputs=ListSalesTaxTemplates,
        run=list_sales_tax_templates,
    ),
    Operation(
        name="report_accounts_receivable",
        title="Accounts receivable",
        description=(
            "What customers owe the assigned company as of `as_of_date` (default today), one "
            "record per open voucher, aged by due date or posting date: `range0` not yet due, "
            "then `range1` to `range5` for 0-30, 31-60, 61-90, 91-120 and over 120 days. "
            "`total_outstanding` covers every record, not only this page. Customer names "
            "aren't in the records; `get_customer` gives them."
        ),
        kind="read",
        inputs=ReportAccountsReceivable,
        run=report_accounts_receivable,
    ),
    Operation(
        name="create_draft_sales_invoice",
        title="Create draft sales invoice",
        description=(
            "Create a draft sales invoice of the assigned company; a person reviews and submits "
            "it in ERPNext. Leave an item's `rate` out to let ERPNext price it from the price "
            "list and its pricing rules; a given rate a pricing rule replaces, and a row left "
            "at rate 0, are named in `warnings`. `posting_date` defaults to today, `due_date` "
            "to the customer's payment terms. A draft with the same customer, posting date "
            "and items is refused unless `allow_duplicate` is true. After an error or a "
            "timeout, list the drafts (`list_sales_invoices` with `state` draft) before "
            "creating again: the first may have been saved."
        ),
        kind="create",
        inputs=CreateDraftSalesInvoice,
        run=create_draft_sales_invoice,
    ),
    Operation(
        name="update_draft_sales_invoice",
        title="Update draft sales invoice",
        description=(
            "Change a draft sales invoice of the assigned company. Give its `name` and its "
            "`modified` as last read; a draft changed since is refused. Give only what "
            "changes: `items` replace all rows; an empty `remarks` or `taxes_and_charges` "
            "clears it, and a cleared tax template takes its tax rows with it. The customer "
            "stays; for another customer, create a new draft."
        ),
        kind="update",
        inputs=UpdateDraftSalesInvoice,
        run=update_draft_sales_invoice,
    ),
]
