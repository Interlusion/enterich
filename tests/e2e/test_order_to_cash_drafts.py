"""Sales invoice drafts end to end (REQ-004-PRS-F005, REQ-004-PRS-F006), and through
them REQ-001's draft rules: bodies, duplicates, stale updates, clearing, warnings and
their comment (REQ-001-PRS-F002 to REQ-001-PRS-F005, REQ-001-PRS-F012,
REQ-001-PRS-F015, REQ-001-PRS-F016)."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.e2e.clock import TIMEZONE, TODAY, freeze
from tests.e2e.mcp import Result, Session, client
from tests.fakes.erpnext import (
    COMMENT_METHOD,
    COMPANY,
    TAXES_METHOD,
    FakeErpnext,
    Received,
    customer,
    error,
    sales_invoice,
    tax_template,
)
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import settings

PATH = "/api/resource/Sales Invoice"
DRAFT = "ACC-SINV-2026-00010"
MODIFIED = "2026-10-28 11:00:00.000000"
VAT_ROWS = [
    {
        "charge_type": "On Net Total",
        "account_head": "1776 - VAT 19% - EX",
        "description": "VAT 19%",
        "rate": 19.0,
        "included_in_print_rate": 0,
        "cost_center": "Main - EX",
    }
]
ONE_ITEM = [{"item_code": "SKU-1", "qty": 2}]


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


def invoice_row(code: str, qty: float, rate: float) -> dict[str, Any]:
    return {
        "doctype": "Sales Invoice Item",
        "item_code": code,
        "qty": qty,
        "rate": rate,
        "amount": qty * rate,
        "uom": "Nos",
        "is_free_item": 0,
    }


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.today = TODAY
    erpnext.prices.update({"SKU-1": 50.0, "SKU-2": 20.0, "SKU-3": 10.0})
    erpnext.add("Customer", customer("CUST-0001"))
    erpnext.add("Customer", customer("CUST-0002"))
    erpnext.add("Sales Taxes and Charges Template", tax_template("VAT 19% - EX"))
    zero = [{**VAT_ROWS[0], "account_head": "1776 - VAT 0% - EX", "rate": 0.0}]
    erpnext.add("Sales Taxes and Charges Template", tax_template("VAT 0% - EX", taxes=zero))
    erpnext.add(
        "Sales Taxes and Charges Template", tax_template("VAT 19% - OT", company="Other AG")
    )
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00001"))
    erpnext.add(
        "Sales Invoice", sales_invoice("ACC-SINV-2026-00002", docstatus=2, status="Cancelled")
    )
    erpnext.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00003", company="Other AG", docstatus=0, status="Draft"),
    )
    erpnext.add(
        "Sales Invoice",
        sales_invoice(
            DRAFT,
            docstatus=0,
            status="Draft",
            set_posting_time=0,
            posting_date=TODAY,
            modified=MODIFIED,
            items=[
                invoice_row("SKU-1", 1, 50.0),
                invoice_row("SKU-2", 1, 20.0),
                invoice_row("SKU-3", 1, 10.0),
            ],
        ),
    )
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext) -> Iterator[Session]:
    with client(jwks, settings(timezone=TIMEZONE), erp) as c:
        yield Session(c, token(signer))


def create(mcp: Session, **arguments: Any) -> Result:
    return mcp.call(
        "create_draft_sales_invoice", {"customer": "CUST-0001", "items": ONE_ITEM, **arguments}
    )


def update(mcp: Session, name: str = DRAFT, modified: str = MODIFIED, **arguments: Any) -> Result:
    return mcp.call("update_draft_sales_invoice", {"name": name, "modified": modified, **arguments})


def writes(erp: FakeErpnext) -> list[Received]:
    return [r for r in erp.received if r.method in ("POST", "PUT")]


def saves(erp: FakeErpnext) -> list[Received]:
    return [r for r in writes(erp) if r.path.startswith(PATH)]


def comments(erp: FakeErpnext) -> list[dict[str, Any]]:
    return erp.comments


# create_draft_sales_invoice


def test_a_create_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    row = {
        "item_code": "SKU-1",
        "qty": 2,
        "rate": 48,
        "uom": "Box",
        "income_account": "4100 - Services - EX",
        "cost_center": "Main - EX",
    }
    result = create(
        mcp,
        posting_date="2026-11-02",
        due_date="2026-12-02",
        items=[row],
        taxes_and_charges="VAT 19% - EX",
        remarks="Order 4711",
    )
    assert not result.error, result.text
    [post] = saves(erp)
    assert (post.method, post.path) == ("POST", PATH)
    assert post.body == {
        "customer": "CUST-0001",
        "posting_date": "2026-11-02",
        "set_posting_time": 1,
        "due_date": "2026-12-02",
        "items": [row],
        "payment_terms_template": "",
        "taxes_and_charges": "VAT 19% - EX",
        "taxes": VAT_ROWS,
        "remarks": "Order 4711",
        "company": COMPANY,
        "docstatus": 0,
    }


def test_the_template_rows_come_from_erpnext(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp, taxes_and_charges="VAT 19% - EX")
    [taxes] = [r for r in erp.received if r.path == TAXES_METHOD]
    assert taxes.method == "GET"
    assert taxes.params == {
        "master_doctype": "Sales Taxes and Charges Template",
        "master_name": "VAT 19% - EX",
    }


def test_a_create_without_optional_inputs_sends_no_date_and_no_rate(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = create(mcp)
    assert not result.error, result.text
    [post] = saves(erp)
    assert post.body == {
        "customer": "CUST-0001",
        "items": [{"item_code": "SKU-1", "qty": 2}],
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_create_returns_the_draft_with_the_rates_erpnext_set(
    mcp: Session, erp: FakeErpnext
) -> None:
    items = [{"item_code": "SKU-1", "qty": 2}, {"item_code": "SKU-2", "qty": 1, "rate": 25}]
    result = create(mcp, items=items, taxes_and_charges="VAT 19% - EX").data
    name = result["name"]
    assert result == {
        "name": name,
        "modified": erp.docs["Sales Invoice"][name]["modified"],
        "status": "Draft",
        "docstatus": 0,
        "company": COMPANY,
        "customer": "CUST-0001",
        "posting_date": TODAY,
        "due_date": "2026-11-28",
        "currency": "EUR",
        "net_total": 125.0,
        "total_taxes_and_charges": 23.75,
        "grand_total": 148.75,
        "taxes": [
            {
                "account_head": "1776 - VAT 19% - EX",
                "rate": 19.0,
                "tax_amount": 23.75,
                "outside_text": {},
            }
        ],
        "items": [
            {
                "item_code": "SKU-1",
                "qty": 2,
                "rate": 50.0,
                "amount": 100.0,
                "is_free_item": False,
                "outside_text": {},
            },
            {
                "item_code": "SKU-2",
                "qty": 1,
                "rate": 25,
                "amount": 25.0,
                "is_free_item": False,
                "outside_text": {},
            },
        ],
        "url": f"https://erp.example.com/desk/sales-invoice/{name}",
        "warnings": [],
        "truncated": [],
        "outside_text": {},
    }
    assert comments(erp) == []


def test_the_draft_tools_carry_their_annotations_and_say_how_to_retry(mcp: Session) -> None:
    listed = {t["name"]: t for t in mcp.tools()}
    created, updated = listed["create_draft_sales_invoice"], listed["update_draft_sales_invoice"]
    assert created["annotations"]["readOnlyHint"] is False
    assert created["annotations"]["destructiveHint"] is False
    assert updated["annotations"]["destructiveHint"] is True
    assert updated["annotations"]["idempotentHint"] is True
    assert "list_sales_invoices" in created["description"]
    assert "state" in created["description"]


@pytest.mark.parametrize(
    ("arguments", "where"),
    [
        ({"docstatus": 1}, "docstatus"),
        ({"company": "Other AG"}, "company"),
        ({"items": [{"item_code": "SKU-1", "qty": 1, "docstatus": 1}]}, "items.0.docstatus"),
        ({"items": []}, "items"),
        ({"items": [{"item_code": "SKU-1", "qty": 1}] * 21}, "items"),
        ({"items": [{"item_code": "SKU-1", "qty": 1, "rate": 0}]}, "items.0.rate"),
        ({"items": [{"item_code": "SKU-1", "qty": 1, "rate": -5}]}, "items.0.rate"),
        ({"items": [{"item_code": "SKU-1", "qty": 0}]}, "items.0.qty"),
        ({"items": [{"item_code": "SKU-1", "qty": "1.0000001"}]}, "items.0.qty"),
        ({"items": [{"qty": 1}]}, "items.0.item_code"),
        ({"posting_date": "2026-02-30"}, "posting_date"),
        ({"remarks": "x" * 1001}, "remarks"),
        ({"allow_duplicate": "yes"}, "allow_duplicate"),
    ],
)
def test_inputs_outside_the_schema_are_refused_before_erpnext(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], where: str
) -> None:
    result = create(mcp, **arguments)
    assert result.error
    assert where in result.text
    assert erp.received == []


def test_a_template_of_another_company_answers_as_unknown(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, taxes_and_charges="VAT 19% - OT")
    assert result.error
    assert result.text.startswith("taxes_and_charges:")
    assert "doesn't exist" in result.text
    assert writes(erp) == []


@pytest.mark.parametrize(
    ("status", "exc_type"), [(404, "DoesNotExistError"), (403, "PermissionError")]
)
def test_an_unknown_or_unpermitted_template_names_the_input(
    mcp: Session, erp: FakeErpnext, status: int, exc_type: str
) -> None:
    erp.fail("/api/method/frappe.client.get", status, error(status, exc_type, "No"))
    result = create(mcp, taxes_and_charges="VAT 19% - EX")
    assert result.error
    assert "taxes_and_charges" in result.text
    assert "doesn't exist" in result.text
    assert "isn't permitted" in result.text
    assert writes(erp) == []


def test_an_erpnext_refusal_reaches_the_agent(mcp: Session) -> None:
    result = create(mcp, customer="CUST-9999")
    assert result.error
    assert "417 LinkValidationError" in result.text
    assert "Could not find Customer: CUST-9999" in result.text


# Duplicates (REQ-004-PRS-F006, REQ-001-PRS-F005)


def test_the_duplicate_check_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext
) -> None:
    create(mcp)
    create(mcp, posting_date="2026-11-02", customer="CUST-0002")
    first, second = [r for r in erp.received if r.method == "GET" and r.path == PATH]
    assert first.param("fields") == ["name", "items.item_code", "items.qty", "items.is_free_item"]
    assert first.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "=", 0],
        ["customer", "=", "CUST-0001"],
        ["posting_date", "=", TODAY],
    ]
    assert second.param("filters")[2:] == [
        ["customer", "=", "CUST-0002"],
        ["posting_date", "=", "2026-11-02"],
    ]


def test_a_create_sent_again_is_refused_naming_the_first_draft(
    mcp: Session, erp: FakeErpnext
) -> None:
    one, two = {"item_code": "SKU-1", "qty": 2}, {"item_code": "SKU-2", "qty": 1}
    first = create(mcp, items=[one, two]).data
    again = create(mcp, items=[two, one])
    assert again.error
    assert first["name"] in again.text
    assert "allow_duplicate" in again.text
    assert len(saves(erp)) == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"items": [{"item_code": "SKU-1", "qty": 3}]},
        {"items": [{"item_code": "SKU-2", "qty": 2}]},
        {"items": [*ONE_ITEM, {"item_code": "SKU-2", "qty": 1}]},
        {"posting_date": "2026-11-02"},
        {"customer": "CUST-0002"},
    ],
)
def test_a_create_differing_in_its_match_goes_through_without_warning(
    mcp: Session, erp: FakeErpnext, changed: dict[str, Any]
) -> None:
    create(mcp)
    result = create(mcp, **changed).data
    assert result["warnings"] == []
    assert len(saves(erp)) == 2


def test_a_draft_with_an_added_free_item_still_matches(mcp: Session, erp: FakeErpnext) -> None:
    erp.free_items["SKU-1"] = "GIFT"
    first = create(mcp).data
    again = create(mcp)
    assert again.error
    assert first["name"] in again.text


def test_allow_duplicate_creates_and_leaves_the_warning_on_the_draft(
    mcp: Session, erp: FakeErpnext
) -> None:
    first = create(mcp).data
    second = create(mcp, allow_duplicate=True).data
    [warning] = second["warnings"]
    assert first["name"] in warning
    [comment] = comments(erp)
    assert comment == {
        "reference_doctype": "Sales Invoice",
        "reference_name": second["name"],
        "content": f"Enterich: {warning}",
        "comment_email": "",
        "comment_by": "",
    }
    [call] = [r for r in erp.received if r.path == COMMENT_METHOD]
    assert call.method == "POST"


# Warnings (REQ-001-PRS-F012, REQ-001-PRS-F015, REQ-001-PRS-F016)


def test_a_template_without_tax_warns_on_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, taxes_and_charges="VAT 0% - EX").data
    [warning] = result["warnings"]
    assert "VAT 0% - EX" in warning
    [comment] = comments(erp)
    assert comment["content"] == f"Enterich: {warning}"


def test_a_rate_a_pricing_rule_replaced_warns(mcp: Session, erp: FakeErpnext) -> None:
    erp.rules["SKU-1"] = 45.0
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 2, "rate": 48}]).data
    assert result["items"][0]["rate"] == 45.0
    [warning] = result["warnings"]
    assert "row 1" in warning.lower()
    assert "SKU-1" in warning
    assert "48" in warning
    assert "45" in warning
    assert len(comments(erp)) == 1


def test_a_row_without_a_price_warns(mcp: Session) -> None:
    result = create(mcp, items=[*ONE_ITEM, {"item_code": "SKU-9", "qty": 1}]).data
    assert result["items"][1]["rate"] == 0
    [warning] = result["warnings"]
    assert "row 2" in warning.lower()
    assert "SKU-9" in warning


def test_kept_rates_and_free_items_dont_warn(mcp: Session, erp: FakeErpnext) -> None:
    erp.free_items["SKU-1"] = "GIFT"
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 2, "rate": 48}]).data
    assert [(r["item_code"], r["rate"], r["is_free_item"]) for r in result["items"]] == [
        ("SKU-1", 48, False),
        ("GIFT", 0, True),
    ]
    assert result["warnings"] == []
    assert comments(erp) == []


def test_a_rate_erpnext_only_rounded_doesnt_warn(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 2, "rate": 12.346}]).data
    assert result["items"][0]["rate"] == 12.35
    assert result["warnings"] == []
    assert comments(erp) == []


def test_the_warnings_go_on_the_draft_as_one_comment(mcp: Session, erp: FakeErpnext) -> None:
    items = [*ONE_ITEM, {"item_code": "SKU-9", "qty": 1}]
    result = create(mcp, items=items, taxes_and_charges="VAT 0% - EX").data
    tax, rate = result["warnings"]
    [comment] = comments(erp)
    assert comment["content"] == f"Enterich: {tax}<br>{rate}"


def test_markup_in_a_warning_reaches_erpnext_as_text(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "<img src=x onerror=alert(1)>", "qty": 1}]).data
    [warning] = result["warnings"]
    assert "<img src=x onerror=alert(1)>" in warning
    [comment] = comments(erp)
    assert "<" not in comment["content"]
    assert "&lt;img src=x onerror=alert(1)&gt;" in comment["content"]


def test_a_failing_comment_still_returns_the_draft_and_says_so(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.fail(COMMENT_METHOD, 403, error(403, "PermissionError", "Not permitted"))
    result = create(mcp, taxes_and_charges="VAT 0% - EX").data
    assert result["name"] in erp.docs["Sales Invoice"]
    tax, missing = result["warnings"]
    assert "VAT 0% - EX" in tax
    assert "comment" in missing
    assert comments(erp) == []


# update_draft_sales_invoice


def test_an_update_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    row = {"item_code": "SKU-2", "qty": 4, "rate": 18, "cost_center": "Main - EX"}
    result = update(
        mcp,
        posting_date="2026-11-02",
        due_date="2026-12-02",
        items=[row],
        remarks="Order 4712",
    )
    assert not result.error, result.text
    [put] = saves(erp)
    assert (put.method, put.path) == ("PUT", f"{PATH}/{DRAFT}")
    assert put.body == {
        "posting_date": "2026-11-02",
        "set_posting_time": 1,
        "due_date": "2026-12-02",
        "payment_terms_template": "",
        "payment_schedule": [],
        "items": [row],
        "remarks": "Order 4712",
        "modified": MODIFIED,
    }


def test_an_update_with_a_template_sends_its_rows(mcp: Session, erp: FakeErpnext) -> None:
    update(mcp, taxes_and_charges="VAT 19% - EX")
    [put] = saves(erp)
    assert put.body == {
        "taxes_and_charges": "VAT 19% - EX",
        "taxes": VAT_ROWS,
        "modified": MODIFIED,
    }


def test_clearing_the_template_clears_its_rows(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, taxes_and_charges="", remarks="").data
    [put] = saves(erp)
    assert put.body == {"taxes_and_charges": "", "taxes": [], "remarks": "", "modified": MODIFIED}
    assert result["taxes"] == []
    assert not [r for r in erp.received if r.path == TAXES_METHOD]


@pytest.mark.parametrize("cleared", [{"posting_date": ""}, {"due_date": ""}, {"items": []}])
def test_fields_that_arent_clearable_are_refused(
    mcp: Session, erp: FakeErpnext, cleared: dict[str, Any]
) -> None:
    result = update(mcp, **cleared)
    assert result.error
    assert next(iter(cleared)) in result.text
    assert erp.received == []


def test_an_update_without_a_change_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp)
    assert result.error
    assert "at least one" in result.text
    assert erp.received == []


def test_the_customer_isnt_changed_by_an_update(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, customer="CUST-0002")
    assert result.error
    assert "customer" in result.text
    assert erp.received == []


def test_an_update_returns_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, remarks="Checked").data
    assert result["name"] == DRAFT
    assert result["modified"] == erp.docs["Sales Invoice"][DRAFT]["modified"] != MODIFIED
    assert result["url"] == f"https://erp.example.com/desk/sales-invoice/{DRAFT}"
    assert len(result["items"]) == 3
    assert result["warnings"] == []


def test_a_posting_date_set_by_an_update_is_kept(mcp: Session, erp: FakeErpnext) -> None:
    created = create(mcp).data
    assert created["posting_date"] == TODAY
    dated = update(mcp, created["name"], created["modified"], posting_date="2026-11-02").data
    assert dated["posting_date"] == "2026-11-02"
    erp.today = "2026-10-30"
    later = update(mcp, created["name"], dated["modified"], remarks="Checked").data
    assert later["posting_date"] == "2026-11-02"


def test_rows_given_replace_all_rows(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, items=[{"item_code": "SKU-3", "qty": 5}]).data
    assert [(r["item_code"], r["qty"]) for r in result["items"]] == [("SKU-3", 5)]
    assert len(erp.docs["Sales Invoice"][DRAFT]["items"]) == 1


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("ACC-SINV-2026-00001", "submitted"),
        ("ACC-SINV-2026-00002", "cancelled"),
        ("ACC-SINV-2026-00003", "doesn't exist"),
    ],
)
def test_only_the_companys_drafts_can_be_updated(
    mcp: Session, erp: FakeErpnext, name: str, says: str
) -> None:
    stored = erp.docs["Sales Invoice"][name]
    result = update(mcp, name, stored["modified"], remarks="Changed")
    assert result.error
    assert result.text.startswith("name:")
    assert says in result.text
    assert writes(erp) == []


@pytest.mark.parametrize("sent", ["2026-10-28 11:00:00", "2026-10-28 11:00:00.000000"])
def test_a_modified_on_a_whole_second_is_taken_as_erpnext_gives_it(
    mcp: Session, erp: FakeErpnext, sent: str
) -> None:
    erp.docs["Sales Invoice"][DRAFT]["modified"] = "2026-10-28 11:00:00"
    result = update(mcp, modified=sent, remarks="Checked")
    assert not result.error, result.text
    [put] = saves(erp)
    assert put.body["modified"] == sent


def test_a_stale_update_changes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    before = dict(erp.docs["Sales Invoice"][DRAFT])
    result = update(mcp, modified="2026-10-28 10:00:00.000000", remarks="Changed")
    assert result.error
    assert "changed" in result.text
    assert writes(erp) == []
    assert erp.docs["Sales Invoice"][DRAFT] == before


@pytest.mark.parametrize("stored", ["", None])
def test_a_draft_without_a_usable_modified_is_taken_as_changed(
    mcp: Session, erp: FakeErpnext, stored: str | None
) -> None:
    erp.docs["Sales Invoice"][DRAFT]["modified"] = stored
    result = update(mcp, remarks="Changed")
    assert result.error
    assert "changed" in result.text
    assert writes(erp) == []


def test_a_draft_changed_during_the_update_is_reported_the_same_way(
    mcp: Session, erp: FakeErpnext
) -> None:
    stale = update(mcp, modified="2026-10-28 10:00:00.000000", remarks="Changed")
    message = "Error: Document has been modified after you have opened it."
    erp.fail(f"{PATH}/{DRAFT}", 417, error(417, "TimestampMismatchError", message))
    raced = update(mcp, remarks="Changed")
    assert raced.error
    assert raced.text == stale.text


def test_another_refusal_of_an_update_reaches_the_agent(mcp: Session, erp: FakeErpnext) -> None:
    message = "Due Date cannot be before Posting Date"
    erp.fail(f"{PATH}/{DRAFT}", 417, error(417, "ValidationError", message))
    result = update(mcp, due_date="2026-10-01")
    assert result.error
    assert f"417 ValidationError). ERPNext's message: {message}" in result.text


def test_a_name_with_url_characters_reaches_erpnext_as_one_segment(
    mcp: Session, erp: FakeErpnext
) -> None:
    name = "X?run_method=discard#a/b"
    draft = sales_invoice(name, docstatus=0, status="Draft", modified=MODIFIED)
    erp.add("Sales Invoice", draft)
    result = update(mcp, name, remarks="Changed")
    assert not result.error, result.text
    assert erp.docs["Sales Invoice"][name]["remarks"] == "Changed"
    [put] = saves(erp)
    assert put.path == f"{PATH}/{name}"


def test_an_update_warns_where_a_pricing_rule_replaced_a_rate(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.rules["SKU-2"] = 15.0
    items = [
        {"item_code": "SKU-1", "qty": 1, "rate": 50},
        {"item_code": "SKU-2", "qty": 1, "rate": 19},
    ]
    result = update(mcp, items=items).data
    [warning] = result["warnings"]
    assert "row 2" in warning.lower()
    assert "SKU-2" in warning
    [comment] = comments(erp)
    assert comment["reference_name"] == DRAFT


def test_an_update_to_a_template_without_tax_warns(mcp: Session) -> None:
    result = update(mcp, taxes_and_charges="VAT 0% - EX").data
    [warning] = result["warnings"]
    assert "VAT 0% - EX" in warning


def test_an_update_of_a_large_draft_cuts_its_rows(mcp: Session, erp: FakeErpnext) -> None:
    rows = [invoice_row(f"SKU-{n % 3 + 1}", 1, 10.0) for n in range(150)]
    erp.docs["Sales Invoice"][DRAFT]["items"] = rows
    result = update(mcp, remarks="Checked").data
    assert len(result["items"]) == 100
    assert result["truncated"] == ["items"]
    assert len(erp.docs["Sales Invoice"][DRAFT]["items"]) == 150


def test_rows_at_rate_0_are_named_up_to_20(mcp: Session, erp: FakeErpnext) -> None:
    rows = [invoice_row(f"NP-{n}", 1, 0.0) for n in range(30)]
    erp.docs["Sales Invoice"][DRAFT]["items"] = rows
    result = update(mcp, remarks="Checked").data
    *named, more = result["warnings"]
    assert len(named) == 20
    assert "NP-19" in named[-1]
    assert "10 more rows" in more
    [comment] = comments(erp)
    assert comment["content"].endswith(more)


# Due dates (REQ-001-PRS-F017)


def test_a_due_date_later_than_the_terms_is_saved(mcp: Session) -> None:
    result = create(mcp, due_date="2027-01-31")
    assert not result.error, result.text
    assert result.data["due_date"] == "2027-01-31"


def test_an_update_with_a_due_date_saves_it(mcp: Session, erp: FakeErpnext) -> None:
    created = create(mcp).data  # its schedule comes from the customer's Net 30
    assert erp.docs["Sales Invoice"][created["name"]]["payment_schedule"]
    result = update(mcp, created["name"], created["modified"], due_date="2026-12-15")
    assert not result.error, result.text
    assert result.data["due_date"] == "2026-12-15"


def test_an_update_of_the_posting_date_recounts_the_due_date(
    mcp: Session, erp: FakeErpnext
) -> None:
    created = create(mcp).data
    result = update(mcp, created["name"], created["modified"], posting_date="2026-11-02").data
    assert result["due_date"] == "2026-12-02"
    put = saves(erp)[-1]
    assert put.body == {
        "posting_date": "2026-11-02",
        "set_posting_time": 1,
        "payment_schedule": [],
        "due_date": None,
        "modified": created["modified"],
    }


def test_a_floating_draft_can_be_updated_on_a_later_day(mcp: Session, erp: FakeErpnext) -> None:
    yesterday = "2026-10-28"
    erp.add("Customer", customer("CUST-0003", payment_terms=None))
    draft = sales_invoice(
        "ACC-SINV-2026-00020",
        customer="CUST-0003",
        docstatus=0,
        status="Draft",
        set_posting_time=0,
        posting_date=yesterday,
        due_date=yesterday,
        payment_terms_template=None,
        payment_schedule=[{"due_date": yesterday, "invoice_portion": 100}],
        modified=MODIFIED,
    )
    erp.add("Sales Invoice", draft)
    result = update(mcp, "ACC-SINV-2026-00020", remarks="Checked")
    assert not result.error, result.text
    assert (result.data["posting_date"], result.data["due_date"]) == (TODAY, TODAY)


def test_an_update_without_a_date_keeps_the_due_date(mcp: Session, erp: FakeErpnext) -> None:
    created = create(mcp, due_date="2026-12-20").data
    result = update(mcp, created["name"], created["modified"], remarks="Checked").data
    assert result["due_date"] == "2026-12-20"
    put = saves(erp)[-1]
    assert put.body == {"remarks": "Checked", "modified": created["modified"]}
