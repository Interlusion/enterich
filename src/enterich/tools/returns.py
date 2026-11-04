"""What both sides' return drafts share: credit notes against sales invoices (REQ-004) and
debit notes against purchase invoices (REQ-005), built from ERPNext's return of the
invoice."""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, NamedTuple, cast

from pydantic import Field

from enterich.shapes import Inputs, Name, Quantity, decimal, rows_of
from enterich.tools import Context, Refusal, drafts, get_named

# What the return's own invoice would carry: ERPNext gives a new document these anew
DROPPED = frozenset({"name", "owner"})
RETURN_MATCH = "invoice (return_against)"
# What is left to return, without the binary residue of ERPNext's floating point
PLACES = Decimal("1e-9")


@dataclass(frozen=True)
class Side:
    """What differs between a credit note and a debit note."""

    invoice: str  # the invoice DocType, which a return is too
    refused: Mapping[str, str]  # the invoice's fields that rule a return out, and what they mean
    invoice_update: str  # the operations that change the invoice drafts and the returns
    return_update: str

    @property
    def what(self) -> str:
        return f"the {self.invoice.lower()}"


class Match(NamedTuple):
    """Possible duplicates of a create: their names, what matched, what they are."""

    names: list[str]
    match: str
    kind: str


class ReturnItem(Inputs):
    item_code: Name
    qty: Quantity


ReturnItems = Annotated[list[ReturnItem], Field(min_length=1, max_length=20)]


def _plain(value: Any) -> Any:
    """ERPNext's mapped document without `name`, `owner` and the fields starting with `__`,
    in its rows too: the new draft gets its own."""
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        return {
            k: _plain(v)
            for k, v in mapping.items()
            if k not in DROPPED and not str(k).startswith("__")
        }
    if isinstance(value, list):
        return [_plain(v) for v in cast("list[Any]", value)]
    return value


async def invoice_of(side: Side, context: Context, name: str) -> dict[str, Any]:
    """A submitted invoice of the assigned company that takes a return; the others refused
    before ERPNext maps them (REQ-004-PRS-F007, REQ-005-PRS-F008)."""
    doc = await get_named(
        context, side.invoice, name, field="return_against", what=side.what, company=True
    )
    state = drafts.DOCSTATUS.get(doc.get("docstatus", 0), "a draft")
    if state != "submitted":
        raise Refusal(f"return_against: {name} is {state}; only a submitted invoice is returned.")
    if doc.get("is_return"):
        against = doc.get("return_against")
        raise Refusal(
            f"return_against: {name} is a return itself; give the invoice it returns"
            + (f" ({against})." if against else ".")
        )
    if doc.get("update_stock"):
        raise Refusal(
            f"return_against: {name} updated stock; Enterich drafts no return that updates "
            "stock. A person makes it in ERPNext."
        )
    for field, means in side.refused.items():
        if doc.get(field):
            raise Refusal(
                f"return_against: {name} {means}; Enterich drafts no return of it. A person "
                "makes it in ERPNext."
            )
    return doc


async def return_of(side: Side, context: Context, invoice: dict[str, Any]) -> dict[str, Any]:
    """ERPNext's return of `invoice`, without what a new draft gets anew."""
    return _plain(await context.erpnext.return_of(side.invoice, str(invoice.get("name"))))


def _left(row: Mapping[str, Any]) -> Decimal:
    """What is left to return on a row of ERPNext's return, as a positive number."""
    return max(-decimal(row.get("qty")), Decimal(0)).quantize(PLACES)


def _line(row: Mapping[str, Any], take: Decimal) -> dict[str, Any]:
    """A row of ERPNext's return at `take`; a debit note's row received in full."""
    line = {**row, "qty": -take}
    if "stock_qty" in row:
        line["stock_qty"] = -take * decimal(row.get("conversion_factor") or 1)
    if "received_qty" in row:
        line |= {"received_qty": -take, "rejected_qty": 0}
    return line


def _fixed(invoice: dict[str, Any]) -> bool:
    """A fixed discount or charge, which ERPNext's return credits in full."""
    discount = decimal(invoice.get("discount_amount")) and not decimal(
        invoice.get("additional_discount_percentage")
    )
    charges = any(t.get("charge_type") == "Actual" for t in rows_of(invoice, "taxes"))
    return bool(discount) or charges


def rows(
    invoice: dict[str, Any], mapped: dict[str, Any], items: Sequence[ReturnItem] | None
) -> list[dict[str, Any]]:
    """The rows of ERPNext's return the draft takes: all that is left without `items`; with
    them, each item taken from its paid rows, then its free-item rows, in row order, each up
    to what is left on it. An invoice with a fixed amount is returned only whole."""
    name = invoice.get("name")
    mapped_rows = rows_of(mapped, "items")
    invoiced = sum((decimal(r.get("qty")) for r in rows_of(invoice, "items")), Decimal(0))
    fixed = _fixed(invoice)
    left_over = sum((_left(r) for r in mapped_rows), Decimal(0))
    if fixed and 0 < left_over < invoiced.quantize(PLACES):
        raise Refusal(
            f"return_against: {name} has a fixed discount or charge, which ERPNext's return "
            "credits in full, and was partly returned before; a person makes this return in "
            "ERPNext."
        )
    if items is None:
        taken = [_line(r, _left(r)) for r in mapped_rows if _left(r) > 0]
        if not taken:
            raise Refusal(
                f"return_against: {name} has nothing left to return; submitted returns took "
                "back all of it."
            )
        return taken
    codes = [i.item_code for i in items]
    if twice := sorted({c for c in codes if codes.count(c) > 1}):
        raise Refusal(f"items: give each item once; {', '.join(twice)} is given twice.")
    taken: list[dict[str, Any]] = []
    returned = Decimal(0)
    for item in items:
        found = [r for r in mapped_rows if r.get("item_code") == item.item_code]
        if not found:
            raise Refusal(f"items: {item.item_code} isn't on {name}.")
        left = sum((_left(r) for r in found), Decimal(0))
        if item.qty > left:
            raise Refusal(
                f"items: {drafts.plain(item.qty)} of {item.item_code} can't be returned; "
                f"{drafts.plain(left)} left to return on {name}."
            )
        wanted = item.qty
        for row in sorted(found, key=lambda r: bool(r.get("is_free_item"))):
            take = min(wanted, _left(row))
            if take > 0:
                taken.append(_line(row, take))
                wanted -= take
                returned += take
    if fixed and returned < invoiced:
        raise Refusal(
            f"items: {name} has a fixed discount or charge, which ERPNext's return credits in "
            "full; Enterich returns only all of its items. Leave out `items`, or a person "
            "makes this return in ERPNext."
        )
    return taken


def timed(invoice: Mapping[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """`fields` with the invoice's posting time when they date the return on the invoice's
    day: a return gets the time of its mapping, which may be before the invoice's."""
    same_day = fields.get("posting_date") == invoice.get("posting_date")
    if same_day and invoice.get("posting_time"):
        return {**fields, "posting_time": invoice["posting_time"]}
    return fields


async def same_invoice(side: Side, context: Context, invoice: str) -> list[str]:
    """Draft returns of the assigned company against `invoice` (REQ-004-PRS-F008,
    REQ-005-PRS-F009); ERPNext counts only submitted returns as taken back."""
    found = await context.erpnext.get_list(
        side.invoice,
        fields=("name",),
        filters=[
            ["company", "=", context.settings.company],
            ["docstatus", "=", 0],
            ["is_return", "=", 1],
            ["return_against", "=", invoice],
        ],
        order_by="name asc",
        start=0,
        page_length=drafts.MAX_DUPLICATE_ROWS,
    )
    return [str(row.get("name")) for row in found]


async def create(
    side: Side,
    context: Context,
    name: str,
    items: Sequence[ReturnItem] | None,
    fields: dict[str, Any],
    allow_duplicate: bool,
    also: Callable[[dict[str, Any]], Awaitable[Match | None]] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Save a return draft: ERPNext's return with the rows taken and `fields` over it;
    the saved draft and its warnings. `also` adds a duplicate check of the invoice."""
    invoice = await invoice_of(side, context, name)
    mapped = await return_of(side, context, invoice)
    lines = rows(invoice, mapped, items)
    found = [Match(await same_invoice(side, context, name), RETURN_MATCH, "draft return")]
    if also is not None and (more := await also(invoice)) is not None:
        found.append(more)
    found = [m for m in found if m.names]
    if found and not allow_duplicate:
        raise drafts.refuse_duplicates(*found[0])
    doc = {**mapped, "items": lines, **timed(invoice, fields)}
    saved = await drafts.insert(context, side.invoice, doc)
    return saved, [drafts.duplicate_warning(*m) for m in found]


async def editable(side: Side, context: Context, name: str, modified: str) -> dict[str, Any]:
    """A return draft against an invoice that the agent user created, as last read
    (REQ-001-PRS-F003)."""
    stored = await drafts.editable(context, side.invoice, name, modified, side.what)
    if not stored.get("is_return"):
        raise Refusal(f"name: {name} isn't a return; change it with {side.invoice_update}.")
    if not stored.get("return_against"):
        raise Refusal(
            f"name: {name} is a return against no invoice; Enterich changes only returns "
            "against an invoice. A person changes it in ERPNext."
        )
    return stored


def not_a_return(side: Side, stored: dict[str, Any]) -> None:
    """For the invoice updates: a return's rows are ERPNext's, not the agent's."""
    if stored.get("is_return"):
        raise Refusal(
            f"name: {stored.get('name')} is a return; change it with {side.return_update}."
        )


async def update(
    side: Side,
    context: Context,
    stored: dict[str, Any],
    items: Sequence[ReturnItem] | None,
    fields: dict[str, Any],
) -> dict[str, Any]:
    """An update's body: with `items` or a posting date, the draft's invoice checked as on
    create, the rows from its return and the posting time as on create."""
    if items is None and "posting_date" not in fields:
        return fields
    invoice = await invoice_of(side, context, str(stored.get("return_against")))
    doc: dict[str, Any] = {}
    if items is not None:
        doc["items"] = rows(invoice, await return_of(side, context, invoice), items)
    return {**doc, **timed(invoice, fields)}
