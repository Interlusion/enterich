"""The published tool list (REQ-001-PRS-F006, REQ-001-PRS-NF002): it changes
only together with the area specs. Update with `uv run pytest --snapshot-update`
and review the diff of tests/snapshots/tools.json. Also the side doors of
REQ-001-PRS-F006, which FakeErpnext refuses and records for the integration tests."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
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
        # REQ-001-PRS-F022
        assert "`tax_summary`" in listed[name], name
        assert "after any discount" in listed[name], name
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


# No generic operations (REQ-001-PRS-F006)

# What no input property may take, by its name or title: a DocType, report, method, field
# list, filter or path
GENERIC = {
    *("doctype", "report", "reportname", "method", "methodname", "fields", "fieldlist"),
    *("filter", "filters", "orfilters", "path", "filepath", "file"),
}


def properties(schema: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    """Every property of a JSON schema, those of nested objects, arrays and $defs too."""
    if isinstance(schema, dict):
        yield from cast("dict[str, Any]", schema).get("properties", {}).items()
        for value in cast("dict[str, Any]", schema).values():
            yield from properties(value)
    elif isinstance(schema, list):
        for value in cast("list[Any]", schema):
            yield from properties(value)


def offered(schema: dict[str, Any], defs: dict[str, Any]) -> list[Any]:
    """The values a property takes besides null, empty when it takes any string."""
    if "$ref" in schema:
        return offered(defs[schema["$ref"].removeprefix("#/$defs/")], defs)
    if "anyOf" in schema:
        choices = [offered(s, defs) for s in schema["anyOf"] if s.get("type") != "null"]
        return [] if [] in choices else [v for c in choices for v in c]
    return schema.get("enum", [])


def test_no_input_takes_a_doctype_report_method_field_list_filter_or_path(
    jwks: FakeJwks, signer: Signer, erpnext: FakeErpnext
) -> None:
    with client(jwks, erpnext=erpnext) as c:
        listed = Session(c, token(signer)).tools()
    for tool in listed:
        schema = tool["inputSchema"]
        for name, prop in properties(schema):
            for label in (name, prop.get("title") or ""):
                assert label.lower().replace(" ", "").replace("_", "") not in GENERIC, (
                    tool["name"],
                    name,
                )
            # a party, reference or voucher type is one of a fixed few
            if name.endswith("_type"):
                assert offered(prop, schema.get("$defs", {})), (tool["name"], name)


SI = "/api/resource/Sales%20Invoice"
SAVEDOCS = "/api/method/frappe.desk.form.save.savedocs"
PINV = "erpnext.accounts.doctype.purchase_invoice.purchase_invoice"
# The methods that post, cancel, delete, discard or run a document's methods, or change a
# submitted purchase invoice, by the dotted path ERPNext has them under
DOOR_PATHS = [
    "frappe.client.submit",
    "frappe.client.cancel",
    "frappe.client.delete",
    "frappe.desk.form.save.discard",
    "run_method",
    "run_doc_method",
    "frappe.handler.runserverobj",
    "frappe.desk.reportview.delete_items",
    "frappe.desk.form.linked_with.cancel_all_linked_docs",
    "frappe.model.workflow.apply_workflow",
    f"{PINV}.block_invoice",
    f"{PINV}.unblock_invoice",
    f"{PINV}.change_release_date",
]
DOORS: list[tuple[str, str, Any]] = [
    *[("POST", f"/api/method/{path}", {}) for path in DOOR_PATHS],
    *[("POST", f"/api/v2/method/{path}", {}) for path in DOOR_PATHS],
    *[
        ("POST", f"/api/v2/document/Sales%20Invoice/SINV-1/method/{path.split('.')[-1]}", {})
        for path in DOOR_PATHS
    ],
    ("DELETE", f"{SI}/SINV-1", None),
    ("DELETE", "/api/v2/document/Sales%20Invoice/SINV-1", None),
    ("POST", SI, {"customer": "C-1", "docstatus": 1}),
    ("PUT", f"{SI}/SINV-1", {"docstatus": 2}),
    ("POST", SI, {"customer": "C-1", "amended_from": "SINV-1"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"docstatus": 2}), "action": "Save"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"amended_from": "SINV-1"}), "action": "Save"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"docstatus": 0}), "action": "Submit"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"docstatus": 0}), "action": "Cancel"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"docstatus": 0}), "action": "Update"}),
    ("GET", f"{SI}/SINV-1?run_method=submit", None),
    ("PUT", f"{SI}/SINV-1", {"run_method": "submit"}),
]
# Calls whose names or values only look like a door: names are data
NOT_DOORS: list[tuple[str, str, Any]] = [
    ("GET", f"{SI}/X%3Frun_method%3Ddiscard", None),
    ("GET", f"{SI}/submit", None),
    ("GET", "/api/v2/document/Sales%20Invoice/a%2Fmethod%2Fsubmit", None),
    ("GET", f"{SI}?filters=%5B%5B%22remarks%22%2C%22%3D%22%2C%22run_method%22%5D%5D", None),
    ("GET", "/api/method/frappe.client.get?doctype=Item&name=frappe.client.submit", None),
    ("POST", SI, {"customer": "C-1", "docstatus": 0, "remarks": "cancel, amended_from"}),
    ("POST", SAVEDOCS, {"doc": json.dumps({"docstatus": 0}), "action": "Save"}),
]


async def sent(method: str, path: str, body: Any) -> tuple[FakeErpnext, httpx2.Response]:
    """A fresh fake ERPNext, and its answer to the call."""
    fake = FakeErpnext()
    request = httpx2.Request(method, f"http://erp.example.com{path}", json=body)
    return fake, await fake.handle(request)


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path", "body"), DOORS)
async def test_the_fake_refuses_and_records_each_side_door(
    method: str, path: str, body: Any
) -> None:
    fake, answer = await sent(method, path, body)
    assert answer.status_code == 403
    assert answer.json()["exc_type"] == "PermissionError"
    assert len(fake.doors) == 1
    assert fake.docs == {}


@pytest.mark.anyio
@pytest.mark.parametrize(("method", "path", "body"), NOT_DOORS)
async def test_the_fake_takes_no_name_or_value_for_a_side_door(
    method: str, path: str, body: Any
) -> None:
    fake, answer = await sent(method, path, body)
    assert answer.status_code != 403
    assert fake.doors == []
