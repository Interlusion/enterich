"""What every draft operation shares (REQ-001 Drafts): tax rows from a template, the
duplicate check, the update checks, the warnings and their comment, the result."""

import html
from collections import Counter
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from erpel.erpnext import ErpnextError, Refused
from erpel.shapes import cut_rows, decimal, form_url, rows_of, shape
from erpel.tools import Context, Refusal, get_named

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


def refuse_duplicates(names: Sequence[str], match: str) -> Refusal:
    return Refusal(
        f"allow_duplicate: a draft with the same {match} exists ({named(names)}). Check it "
        "first; to create another anyway, repeat with allow_duplicate true."
    )


def duplicate_warning(names: Sequence[str], match: str) -> str:
    return f"Possible duplicate of {named(names)}: a draft with the same {match}."


async def editable(context: Context, doctype: str, name: str, modified: str, what: str) -> None:
    """Refuse an update of anything but the company's draft as last read (REQ-001-PRS-F003,
    REQ-001-PRS-F004)."""
    stored = await get_named(context, doctype, name, field="name", what=what, company=True)
    state = DOCSTATUS.get(stored.get("docstatus", 0))
    if state is not None:
        raise Refusal(f"name: {name} is {state}; only drafts can be updated.")
    if _timestamp(stored.get("modified")) != _timestamp(modified):
        raise Refusal(STALE)


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


def _number(value: Decimal) -> str:
    return f"{value.normalize():f}"


def rate_warnings(saved: dict[str, Any], given: Sequence[dict[str, Any]] | None) -> list[str]:
    """REQ-001-PRS-F016: given rates a pricing rule replaced, and rows left at rate 0.
    Rows match in the order given; free-item rows don't take part. A rate ERPNext only
    rounded to the currency's precision has no rule in `pricing_rules`."""
    rows = [r for r in rows_of(saved, "items") if not r.get("is_free_item")]
    warnings: list[str] = []
    for number, row in enumerate(rows, start=1):
        code, rate = row.get("item_code"), decimal(row.get("rate"))
        asked = given[number - 1].get("rate") if given and number <= len(given) else None
        if asked is not None and Decimal(asked) != rate and row.get("pricing_rules"):
            warnings.append(
                f"Row {number} ({code}): rate {_number(Decimal(asked))} was given, but ERPNext "
                f"saved {_number(rate)}; a pricing rule set it."
            )
        elif rate == 0:
            warnings.append(
                f"Row {number} ({code}) was saved at rate 0: the price list has no price for "
                "the item. Give the rate."
            )
    if len(warnings) > MAX_ROW_WARNINGS:
        more = len(warnings) - MAX_ROW_WARNINGS
        warnings = [
            *warnings[:MAX_ROW_WARNINGS],
            f"{more} more rows have such a warning; get the draft to see their rates.",
        ]
    return warnings


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
        "items": [shape(r, ROW_FIELDS, flags={"is_free_item"}) for r in items],
        "url": form_url(context.settings.erpnext_public_url, doctype, name),
        "warnings": await comment(context, doctype, name, warnings),
        "truncated": [t for t, cut in (("items", items_cut), ("taxes", taxes_cut)) if cut],
    }
