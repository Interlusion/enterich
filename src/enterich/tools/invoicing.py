"""The reads both sides of invoicing share: parties with their addresses, invoices, tax
templates and the aged report (REQ-004 for sales, REQ-005 for purchases)."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from enterich.shapes import (
    InvoiceState,
    cut_rows,
    cut_texts,
    decimal,
    form_url,
    invoice_state,
    like_pattern,
    page,
    rows_of,
    shape,
    split_outside,
    today,
)
from enterich.tools import Context, Table, get_document, get_named, report_rows

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
INVOICE_DETAIL_FIELDS = (
    "taxes_and_charges",
    "total_taxes_and_charges",
    "return_against",
    "remarks",
)
TEMPLATE_FIELDS = ("name", "title", "is_default", "tax_category", "disabled")
AGEING = tuple(f"range{i}" for i in range(6))  # range0: not yet due; then ERPNext's 30, 60, 90, 120
AGEING_BASED_ON = {"due_date": "Due Date", "posting_date": "Posting Date"}
MAX_ADDRESSES = 100
# For each operation whose result has tax rows (REQ-001 Results)
TAX_RATE_NOTE = (
    "A tax row's `rate` is the rate saved on it; an item with an item tax template is taxed "
    "at that template's rate on the rows whose accounts it lists, or not by such a row, so "
    "`rate` need not be any item's rate: take the tax from `tax_amount`. `tax_summary` "
    "adds up the tax per tax row and the rate the items were taxed at, with the amount "
    "taxed (`taxable_amount`), after any discount, where `tax_amount` is before one on the "
    "grand total; an item at 0 % there wasn't taxed by that row."
)
TAX_SUMMARY_FIELDS = ("account_head", "rate", "taxable_amount", "tax_amount")
# A tax summary converted from the company's currency is rounded to the cent
CENT = Decimal("0.01")
PURCHASE_TAX_RATE_NOTE = (
    f"{TAX_RATE_NOTE} A row with `add_deduct_tax` Deduct is subtracted from the total, and "
    "the tax of one with `category` Valuation isn't in it."
)

AgeingBasedOn = Literal["due_date", "posting_date"]  # inlined in the schema, unlike `type`


@dataclass(frozen=True)
class Side:
    """What differs between the sales and the purchase side."""

    party: str  # the party DocType, and the report's party type
    party_field: str  # the party's field on an invoice
    party_fields: tuple[str, ...]
    party_outside: frozenset[str]
    invoice: str
    invoice_fields: tuple[str, ...]
    invoice_outside: frozenset[str]
    item_fields: tuple[str, ...]
    item_outside: frozenset[str]
    tax_fields: tuple[str, ...]
    template: str
    report: str
    aged_fields: tuple[str, ...]
    aged_outside: frozenset[str] = frozenset()

    @property
    def what_party(self) -> str:
        return f"the {self.party.lower()}"

    @property
    def what_invoice(self) -> str:
        return f"the {self.invoice.lower()}"


def _party(side: Side, doc: dict[str, Any]) -> dict[str, Any]:
    return shape(doc, side.party_fields, outside=side.party_outside, flags={"disabled"})


def _invoice(side: Side, doc: dict[str, Any]) -> dict[str, Any]:
    return shape(doc, side.invoice_fields, outside=side.invoice_outside, flags={"is_return"})


async def list_parties(
    side: Side,
    context: Context,
    *,
    search: str | None,
    include_disabled: bool,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    or_filters: list[list[Any]] = []
    if search is not None:
        pattern = like_pattern(search)
        or_filters = [["name", "like", pattern], [f"{side.party_field}_name", "like", pattern]]
    rows = await context.erpnext.get_list(
        side.party,
        fields=side.party_fields,
        filters=[] if include_disabled else [["disabled", "=", 0]],
        or_filters=or_filters,
        order_by="name asc",
        start=offset,
        page_length=limit + 1,
    )
    return page([_party(side, row) for row in rows], offset, limit)


async def get_party(side: Side, context: Context, name: str) -> dict[str, Any]:
    doc = await get_named(context, side.party, name, field="name", what=side.what_party)
    name = str(doc.get("name", name))
    addresses = await context.erpnext.get_list(
        "Address",
        fields=ADDRESS_FIELDS,
        filters=[
            ["Dynamic Link", "link_doctype", "=", side.party],
            ["Dynamic Link", "link_name", "=", name],
        ],
        order_by="name asc",
        start=0,
        page_length=MAX_ADDRESSES + 1,
    )
    record = shape(
        doc, (*side.party_fields, "payment_terms"), outside=side.party_outside, flags={"disabled"}
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
            "url": form_url(context.settings.erpnext_public_url, side.party, name),
            "truncated": ["addresses"] if len(addresses) > MAX_ADDRESSES else [],
            "outside_text": outside,
        }
    )


async def list_invoices(
    side: Side,
    context: Context,
    *,
    party: str | None,
    state: InvoiceState | None,
    from_date: date | None,
    to_date: date | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if party is not None:
        filters.append([side.party_field, "=", party])
    if state is not None:
        filters += invoice_state(state, today(context.settings.timezone))
    if from_date is not None:
        filters.append(["posting_date", ">=", from_date.isoformat()])
    if to_date is not None:
        filters.append(["posting_date", "<=", to_date.isoformat()])
    rows = await context.erpnext.get_list(
        side.invoice,
        fields=side.invoice_fields,
        filters=filters,
        order_by="posting_date desc, name desc",
        start=offset,
        page_length=limit + 1,
    )
    return page([_invoice(side, row) for row in rows], offset, limit)


def tax_summary(doc: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    """ERPNext's tax per item row and tax row added up per tax row and rate, in the order of
    the rows and by rate, highest first, without entries of nothing; cut at 100 entries
    (REQ-001-PRS-F022). ERPNext negates a Deduct row's tax per item, which is turned back to
    the sign of the row's `tax_amount`; the amount taxed it negates only when it computes
    it, not in v16's migration of older invoices or for tax withholding, so a Deduct row's
    takes the sign of its item row's amount. ERPNext stores them in the company's currency;
    on an invoice in another, the sums are divided by its conversion rate, as ERPNext's
    printed tax breakup does."""
    taxes = rows_of(doc, "taxes")
    conversion = decimal(doc.get("conversion_rate")) or Decimal(1)
    numbers = {row.get("name"): number for number, row in enumerate(taxes)}
    negative = {r.get("name") for r in rows_of(doc, "items") if decimal(r.get("amount")) < 0}
    sums: dict[tuple[int, Decimal], tuple[Decimal, Decimal]] = {}
    for detail in rows_of(doc, "item_wise_tax_details"):
        number = numbers.get(detail.get("tax_row"))
        if number is None:
            continue
        taxable, tax = decimal(detail.get("taxable_amount")), decimal(detail.get("amount"))
        if taxes[number].get("add_deduct_tax") == "Deduct":
            tax = -tax
            taxable = -abs(taxable) if detail.get("item_row") in negative else abs(taxable)
        key = (number, decimal(detail.get("rate")))
        base, total = sums.get(key, (Decimal(0), Decimal(0)))
        sums[key] = (base + taxable, total + tax)
    if conversion != 1:
        sums = {
            key: ((base / conversion).quantize(CENT), (tax / conversion).quantize(CENT))
            for key, (base, tax) in sums.items()
        }
    entries = [
        shape(
            {
                "account_head": taxes[number].get("account_head"),
                "rate": float(rate),
                "taxable_amount": float(base),
                "tax_amount": float(tax),
            },
            TAX_SUMMARY_FIELDS,
        )
        for (number, rate), (base, tax) in sorted(sums.items(), key=lambda s: (s[0][0], -s[0][1]))
        if base or tax
    ]
    return cut_rows(entries)


async def get_invoice(side: Side, context: Context, name: str) -> dict[str, Any]:
    return await get_document(
        context,
        side.invoice,
        name,
        what=side.what_invoice,
        fields=(*side.invoice_fields, *INVOICE_DETAIL_FIELDS),
        outside=side.invoice_outside,
        flags={"is_return"},
        tables={
            "items": Table(side.item_fields, side.item_outside),
            "taxes": Table(side.tax_fields),
        },
        derived={"tax_summary": tax_summary},
    )


async def list_templates(
    side: Side, context: Context, *, include_disabled: bool, limit: int, offset: int
) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if not include_disabled:
        filters.append(["disabled", "=", 0])
    rows = await context.erpnext.get_list(
        side.template,
        fields=TEMPLATE_FIELDS,
        filters=filters,
        order_by="name asc",
        start=offset,
        page_length=limit + 1,
    )
    records = [shape(row, TEMPLATE_FIELDS, flags={"is_default", "disabled"}) for row in rows]
    return page(records, offset, limit)


async def aged_report(
    side: Side,
    context: Context,
    *,
    as_of_date: date | None,
    party: str | None,
    ageing_based_on: AgeingBasedOn,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    filters: dict[str, Any] = {
        "company": context.settings.company,
        "report_date": (as_of_date or today(context.settings.timezone)).isoformat(),
        "party_type": side.party,
        "ageing_based_on": AGEING_BASED_ON[ageing_based_on],
        "age_as_on": "Report Date",
        "range": "30, 60, 90, 120",
    }
    if party is not None:
        filters["party"] = [party]
    rows = await report_rows(context, side.report, filters)
    total: Decimal = sum((decimal(row.get("outstanding")) for row in rows), Decimal(0))
    shown = rows[offset : offset + limit + 1]
    records = [
        {
            **split_outside({f: row.get(f) for f in side.aged_fields}, side.aged_outside),
            "ageing": {r: row.get(r) for r in AGEING},
        }
        for row in shown
    ]
    return {**page(records, offset, limit), "total_outstanding": total}
