"""Master data: items (REQ-003)."""

from typing import Any, cast

from erpel.shapes import (
    Flag,
    Inputs,
    Limit,
    Name,
    Offset,
    Search,
    cut_rows,
    form_url,
    like_pattern,
    page,
    split_outside,
)
from erpel.tools import Context, Operation, get_named

LIST_FIELDS = ["item_code", "item_name", "item_group", "stock_uom", "is_stock_item", "disabled"]
OUTSIDE = {"item_name", "description"}
DEFAULT_FIELDS = ("income_account", "expense_account", "selling_cost_center", "buying_cost_center")
TAX_FIELDS = ("item_tax_template", "tax_category", "valid_from")


class ListItems(Inputs):
    search: Search | None = None
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class GetItem(Inputs):
    item_code: Name


def _item(doc: dict[str, Any]) -> dict[str, Any]:
    record = {
        "item_code": doc.get("item_code"),
        "item_name": doc.get("item_name"),
        "item_group": doc.get("item_group"),
        "stock_uom": doc.get("stock_uom"),
        "is_stock_item": bool(doc.get("is_stock_item")),
        "disabled": bool(doc.get("disabled")),
    }
    return split_outside(record, OUTSIDE)


def _rows(doc: dict[str, Any], table: str) -> list[dict[str, Any]]:
    rows = doc.get(table)
    return cast("list[dict[str, Any]]", rows) if isinstance(rows, list) else []


async def list_items(inputs: ListItems, context: Context) -> dict[str, Any]:
    filters = [] if inputs.include_disabled else [["disabled", "=", 0]]
    or_filters = []
    if inputs.search is not None:
        pattern = like_pattern(inputs.search)
        or_filters = [["item_code", "like", pattern], ["item_name", "like", pattern]]
    rows = await context.erpnext.get_list(
        "Item",
        fields=LIST_FIELDS,
        filters=filters,
        or_filters=or_filters,
        order_by="name asc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    return page([_item(row) for row in rows], inputs.offset, inputs.limit)


async def get_item(inputs: GetItem, context: Context) -> dict[str, Any]:
    doc = await get_named(context, "Item", inputs.item_code, field="item_code", what="the item")
    company = context.settings.company
    defaults = next((r for r in _rows(doc, "item_defaults") if r.get("company") == company), None)
    taxes, cut = cut_rows(_rows(doc, "taxes"))
    record = _item(doc)
    return {
        **record,
        **{field: defaults and defaults.get(field) for field in DEFAULT_FIELDS},
        "item_tax_templates": [
            split_outside({k: row.get(k) for k in TAX_FIELDS}, set()) for row in taxes
        ],
        "modified": doc.get("modified"),
        # ERPNext finds names case-insensitively; the link carries the stored one.
        "url": form_url(
            context.settings.erpnext_public_url, "Item", str(doc.get("name", inputs.item_code))
        ),
        "truncated": ["item_tax_templates"] if cut else [],
        "outside_text": {**record["outside_text"], "description": doc.get("description")},
    }


OPERATIONS: list[Operation[Any]] = [
    Operation(
        name="list_items",
        title="List items",
        description=(
            "List items, ordered by item code. `search` matches part of the item code or name. "
            "Disabled items are left out unless `include_disabled` is true. Use the item codes "
            "in drafts; `has_more` says whether `offset` can fetch more."
        ),
        kind="read",
        inputs=ListItems,
        run=list_items,
    ),
    Operation(
        name="get_item",
        title="Get item",
        description=(
            "Get one item by its exact item code, with the accounts and cost centres the "
            "assigned company uses for it and its item tax templates."
        ),
        kind="read",
        inputs=GetItem,
        run=get_item,
    ),
]
