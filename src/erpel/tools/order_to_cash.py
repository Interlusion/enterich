"""Order to cash: customers, sales invoices, sales tax templates, receivables (REQ-004)."""

from typing import Annotated, Any, Literal, Self

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
    in_order,
    today,
)
from erpel.tools import Context, Operation, drafts, invoicing
from erpel.tools.invoicing import AgeingBasedOn

SALES = invoicing.Side(
    party="Customer",
    party_field="customer",
    party_fields=(
        "name",
        "customer_name",
        "customer_type",
        "customer_group",
        "tax_id",
        "default_currency",
        "disabled",
    ),
    party_outside=frozenset({"customer_name", "tax_id"}),
    invoice="Sales Invoice",
    invoice_fields=(
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
    ),
    invoice_outside=frozenset({"customer_name", "remarks"}),
    item_fields=(
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
    ),
    item_outside=frozenset({"item_name", "description"}),
    tax_fields=("charge_type", "account_head", "rate", "tax_amount", "description"),
    template="Sales Taxes and Charges Template",
    report="Accounts Receivable",
    aged_fields=(
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
    ),
)
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
    ageing_based_on: AgeingBasedOn = "due_date"
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


async def list_customers(inputs: ListCustomers, context: Context) -> dict[str, Any]:
    return await invoicing.list_parties(
        SALES,
        context,
        search=inputs.search,
        include_disabled=inputs.include_disabled,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def get_customer(inputs: GetCustomer, context: Context) -> dict[str, Any]:
    return await invoicing.get_party(SALES, context, inputs.name)


async def list_sales_invoices(inputs: ListSalesInvoices, context: Context) -> dict[str, Any]:
    return await invoicing.list_invoices(
        SALES,
        context,
        party=inputs.customer,
        state=inputs.state,
        from_date=inputs.from_date,
        to_date=inputs.to_date,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def get_sales_invoice(inputs: GetSalesInvoice, context: Context) -> dict[str, Any]:
    return await invoicing.get_invoice(SALES, context, inputs.name)


async def list_sales_tax_templates(
    inputs: ListSalesTaxTemplates, context: Context
) -> dict[str, Any]:
    return await invoicing.list_templates(
        SALES,
        context,
        include_disabled=inputs.include_disabled,
        limit=inputs.limit,
        offset=inputs.offset,
    )


async def report_accounts_receivable(
    inputs: ReportAccountsReceivable, context: Context
) -> dict[str, Any]:
    return await invoicing.aged_report(
        SALES,
        context,
        as_of_date=inputs.as_of_date,
        party=inputs.customer,
        ageing_based_on=inputs.ageing_based_on,
        limit=inputs.limit,
        offset=inputs.offset,
    )


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
        taxes = await drafts.tax_rows(context, SALES.template, inputs.taxes_and_charges)
    doc = drafts.due_dates(_invoice_body(inputs, taxes))
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
    stored = await drafts.editable(
        context, "Sales Invoice", inputs.name, inputs.modified, "the sales invoice"
    )
    taxes = None
    if inputs.taxes_and_charges:
        taxes = await drafts.tax_rows(context, SALES.template, inputs.taxes_and_charges)
    day = today(context.settings.timezone)
    doc = drafts.due_dates(_invoice_body(inputs, taxes), stored, day)
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
