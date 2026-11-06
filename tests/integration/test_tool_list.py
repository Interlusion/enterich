"""The published tool list (REQ-001-PRS-F006, REQ-001-PRS-NF002): it changes
only together with the area specs. Update with `uv run pytest --snapshot-update`
and review the diff of tests/snapshots/tools.json."""

from pathlib import Path
from typing import Any

from syrupy.assertion import SnapshotAssertion
from syrupy.extensions.json import JSONSnapshotExtension
from syrupy.location import PyTestLocation
from syrupy.types import SnapshotIndex

from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.integration.mcp import Session, client


class ToolsJson(JSONSnapshotExtension):
    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        return str(Path(__file__).parent.parent / "snapshots")

    @classmethod
    def get_snapshot_name(cls, *, test_location: PyTestLocation, index: SnapshotIndex = 0) -> str:
        return "tools"


def test_the_tool_list_matches_the_snapshot(
    jwks: FakeJwks, signer: Signer, erpnext: FakeErpnext, snapshot: SnapshotAssertion
) -> None:
    with client(jwks, erpnext=erpnext) as c:
        listed: list[dict[str, Any]] = Session(c, token(signer)).tools()
    assert sorted(listed, key=lambda t: t["name"]) == snapshot(extension_class=ToolsJson)


# The operations whose results carry tax rows (REQ-001 Results)
WITH_TAX_ROWS = {
    f"{verb}_{what}"
    for verb in ("create_draft", "update_draft")
    for what in ("sales_invoice", "purchase_invoice", "sales_return", "purchase_return")
} | {"get_sales_invoice", "get_purchase_invoice"}


def test_each_tool_with_tax_rows_says_what_their_rate_is(
    jwks: FakeJwks, signer: Signer, erpnext: FakeErpnext
) -> None:
    with client(jwks, erpnext=erpnext) as c:
        listed = {t["name"]: t["description"] for t in Session(c, token(signer)).tools()}
    assert set(listed) >= WITH_TAX_ROWS
    for name in WITH_TAX_ROWS:
        assert "item tax template" in listed[name], name
        assert "`tax_amount`" in listed[name], name
        if "purchase" in name:
            assert "`add_deduct_tax` Deduct" in listed[name], name
            assert "`category` Valuation" in listed[name], name


def test_invoice_creates_say_to_give_a_tax_template(
    jwks: FakeJwks, signer: Signer, erpnext: FakeErpnext
) -> None:
    with client(jwks, erpnext=erpnext) as c:
        listed = {t["name"]: t["description"] for t in Session(c, token(signer)).tools()}
    for side in ("sales", "purchase"):
        description = listed[f"create_draft_{side}_invoice"]
        assert "Give `taxes_and_charges`" in description
        assert "no tax rows from a default template or a Tax Rule" in description
        assert f"`list_{side}_tax_templates`" in description
