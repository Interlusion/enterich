"""What every draft operation shares (REQ-001 Drafts): tax rows from a template, the
duplicate check, the update checks, the warnings and their comment, the result."""

import html
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from erpel.erpnext import ErpnextError, Refused
from erpel.shapes import cut_rows, decimal, form_url, rows_of, shape
from erpel.tools import Context, Refusal, get_named, unknown_name

MAX_DUPLICATE_ROWS = 1000
MAX_NAMED = 5
MAX_ROW_WARNINGS = 20
STALE = (
    "modified: the draft has changed since it was read; get it again and repeat the update "
    "with its new `modified`."
)
DOCSTATUS = {1: "submitted", 2: "cancelled"}
ROW_FIELDS = ("item_code", "qty", "rate", "amount", "is_free_item")
TAX_FIELDS = ("account_head", "rate", "tax_amount")


async def tax_rows(context: Context, doctype: str, template: str) -> list[dict[str, Any]]:
    """The rows of a tax template of the assigned company, as ERPNext copies them."""
    await get_named(
        context, doctype, template, field="taxes_and_charges", what="the tax template", company=True
    )
    return await context.erpnext.tax_rows(doctype, template)


async def duplicates(
    context: Context,
    doctype: str,
    filters: Sequence[Sequence[Any]],
    items: Sequence[dict[str, Any]],
) -> list[str]:
    """Drafts of the assigned company matching `filters` with the same item codes and
    quantities, in any order, leaving out free-item rows a pricing rule added."""
    rows = await context.erpnext.get_list(
        doctype,
        fields=("name", "items.item_code", "items.qty", "items.is_free_item"),
        filters=[["company", "=", context.settings.company], ["docstatus", "=", 0], *filters],
        order_by="name asc",
        start=0,
        page_length=MAX_DUPLICATE_ROWS,
    )
    drafts: dict[str, Counter[tuple[str, Decimal]]] = {}
    for row in rows:
        found = drafts.setdefault(str(row.get("name")), Counter())
        if row.get("item_code") is not None and not row.get("is_free_item"):
            found[(str(row["item_code"]), decimal(row.get("qty")))] += 1
    wanted = Counter((str(i["item_code"]), Decimal(i["qty"])) for i in items)
    return sorted(name for name, found in drafts.items() if found == wanted)


def named(names: Sequence[str]) -> str:
    shown = ", ".join(names[:MAX_NAMED])
    return shown + (f" and {len(names) - MAX_NAMED} more" if len(names) > MAX_NAMED else "")


def refuse_duplicates(names: Sequence[str], match: str, kind: str = "draft") -> Refusal:
    return Refusal(
        f"allow_duplicate: a {kind} with the same {match} exists ({named(names)}). Check it "
        "first; to create another anyway, repeat with allow_duplicate true."
    )


def duplicate_warning(names: Sequence[str], match: str, kind: str = "draft") -> str:
    return f"Possible duplicate of {named(names)}: a {kind} with the same {match}."


async def editable(
    context: Context,
    doctype: str,
    name: str,
    modified: str,
    what: str,
    only: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The company's draft as last read; refuse an update of anything else (REQ-001-PRS-F003,
    REQ-001-PRS-F004). A document without the values in `only` answers as an unknown one,
    before its state is told."""
    stored = await get_named(context, doctype, name, field="name", what=what, company=True)
    if any(stored.get(field) != value for field, value in (only or {}).items()):
        raise unknown_name("name", what, name)
    state = DOCSTATUS.get(stored.get("docstatus", 0))
    if state is not None:
        raise Refusal(f"name: {name} is {state}; only drafts can be updated.")
    if _timestamp(stored.get("modified")) != _timestamp(modified):
        raise Refusal(STALE)
    return stored


def _timestamp(value: Any) -> datetime | None:
    """`modified` as ERPNext compares it (`check_if_latest`): parsed, not as text."""
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


async def save_update(
    context: Context, doctype: str, name: str, doc: dict[str, Any]
) -> dict[str, Any]:
    try:
        return await context.erpnext.update(doctype, name, doc)
    except Refused as refused:
        if refused.exc_type == "TimestampMismatchError":
            raise Refusal(STALE) from None
        raise


def due_dates(
    doc: dict[str, Any], stored: dict[str, Any] | None = None, day: date | None = None
) -> dict[str, Any]:
    """REQ-001-PRS-F017: an invoice body with what keeps its due date the given one, or the
    one ERPNext counts from the payment terms and the current dates, as the form does.
    `stored` is the draft an update changes, `day` today; on create both are None."""
    if "due_date" in doc:
        doc = {**doc, "payment_terms_template": ""}  # the given date is the only term
    if stored is None:
        return doc
    # A draft without a fixed posting date gets today's at this save.
    moves = not stored.get("set_posting_time") and stored.get("posting_date") != str(day)
    if moves or {"due_date", "posting_date", "bill_date"} & doc.keys():
        doc = {**doc, "payment_schedule": []}  # ERPNext builds it anew only when empty
        if "due_date" not in doc:
            doc["due_date"] = None  # counted again from the terms
    return doc


def plain(value: Decimal) -> str:
    """An amount as the warnings print it: 15, 15.01."""
    return f"{value.normalize():f}"


def row_warnings(
    saved: dict[str, Any], given: Sequence[dict[str, Any]] | None, account: str | None = None
) -> list[str]:
    """REQ-001-PRS-F016: given rates a pricing rule replaced, and rows left at rate 0; with
    `account`, given accounts ERPNext replaced (REQ-005-PRS-F007). Rows match in the order
    given; free-item rows don't take part. A rate ERPNext only rounded to the currency's
    precision has no rule in `pricing_rules`."""
    rows = [r for r in rows_of(saved, "items") if not r.get("is_free_item")]
    named: list[list[str]] = []
    for number, row in enumerate(rows, start=1):
        warnings: list[str] = []
        code, rate = row.get("item_code"), decimal(row.get("rate"))
        sent = given[number - 1] if given and number <= len(given) else {}
        asked = sent.get("rate")
        if asked is not None and Decimal(asked) != rate and row.get("pricing_rules"):
            warnings.append(
                f"Row {number} ({code}): rate {plain(Decimal(asked))} was given, but ERPNext "
                f"saved {plain(rate)}; a pricing rule set it."
            )
        elif rate == 0:
            warnings.append(
                f"Row {number} ({code}) was saved at rate 0: the price list has no price for "
                "the item. Give the rate."
            )
        wanted = sent.get(account) if account else None
        # ERPNext saves a link in the stored name's case.
        if account and wanted is not None and _folded(row.get(account)) != _folded(wanted):
            label = account.replace("_", " ")
            warnings.append(
                f"Row {number} ({code}): {label} {wanted} was given, but ERPNext saved "
                f"{row.get(account)}."
            )
        if warnings:
            named.append(warnings)
    shown = [w for row in named[:MAX_ROW_WARNINGS] for w in row]
    if len(named) > MAX_ROW_WARNINGS:
        more = len(named) - MAX_ROW_WARNINGS
        shown.append(f"{more} more rows have such a warning; get the draft to check them.")
    return shown


def _folded(value: Any) -> str:
    return str(value or "").casefold()


def tax_warning(saved: dict[str, Any], template: str | None) -> list[str]:
    """REQ-001-PRS-F012."""
    if template and decimal(saved.get("total_taxes_and_charges")) == 0:
        return [
            f"Tax template {template} was given, but the tax total is 0; check the template "
            "and the items' tax templates."
        ]
    return []


async def comment(context: Context, doctype: str, name: str, warnings: list[str]) -> list[str]:
    """REQ-001-PRS-F015: the warnings on the draft as plain text; a failure is one more."""
    if not warnings:
        return warnings
    # The content is HTML: each warning escaped, one per line
    content = "Erpel: " + "<br>".join(html.escape(w, quote=False) for w in warnings)
    try:
        await context.erpnext.add_comment(doctype, name, content)
    except ErpnextError as exc:
        return [*warnings, f"These warnings couldn't be added to the draft as a comment: {exc}"]
    return warnings


async def result(
    context: Context,
    doctype: str,
    saved: dict[str, Any],
    fields: Sequence[str],
    warnings: list[str],
    row_fields: Sequence[str] = ROW_FIELDS,
) -> dict[str, Any]:
    """The draft as REQ-001's Results say, after its warnings went on the draft; its rows
    cut as a get cuts them (REQ-001-PRS-NF003)."""
    name = str(saved.get("name"))
    record = shape(saved, ("name", "modified", "status", "docstatus", "company", *fields))
    taxes, taxes_cut = cut_rows(rows_of(saved, "taxes"))
    items, items_cut = cut_rows(rows_of(saved, "items"))
    return {
        **record,
        "taxes": [shape(r, TAX_FIELDS) for r in taxes],
        "items": [shape(r, row_fields, flags={"is_free_item"}) for r in items],
        "url": form_url(context.settings.erpnext_public_url, doctype, name),
        "warnings": await comment(context, doctype, name, warnings),
        "truncated": [t for t, cut in (("items", items_cut), ("taxes", taxes_cut)) if cut],
    }
