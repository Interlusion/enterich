"""Master data against the seeded site (REQ-003-PRS-F001); also that Enterich reaches the
site at all: the configured Host selects it, and the agent's key opens its records."""

from tests.e2e.seed import Seed
from tests.integration.mcp import Session


def test_list_items_finds_the_seeded_item(mcp: Session, seeded: Seed) -> None:
    records = mcp.call("list_items", {"search": "SKU"}).data["records"]
    [item] = [r for r in records if r["item_code"] == seeded.item]
    assert (item["item_group"], item["stock_uom"]) == ("Products", "Nos")
    assert item["outside_text"] == {"item_name": "Widget SKU-1"}


def test_get_item(mcp: Session, seeded: Seed) -> None:
    item = mcp.call("get_item", {"item_code": seeded.item}).data
    assert (item["item_code"], item["is_stock_item"], item["disabled"]) == (
        seeded.item,
        True,
        False,
    )
    assert item["url"].endswith(f"/desk/item/{seeded.item}")
