"""Sales invoice drafts (REQ-004-PRS-F005, REQ-004-PRS-F006), and through them
REQ-001's draft rules: bodies, duplicates, stale updates, clearing, warnings and their
comment, the limit of drafts per hour (REQ-001-PRS-F002, REQ-001-PRS-F003,
REQ-001-PRS-F004, REQ-001-PRS-F005, REQ-001-PRS-F012, REQ-001-PRS-F015,
REQ-001-PRS-F016, REQ-001-PRS-F019, REQ-001-PRS-F020, REQ-001-PRS-F021), and the
tax summary (REQ-001-PRS-F022)."""

import re
import time
from typing import Any

import pytest

from enterich import tools
from tests.conftest import Logs
from tests.fakes.erpnext import (
    AGENT,
    COMMENT_METHOD,
    COMPANY,
    LOGGED_USER_METHOD,
    TAXES_METHOD,
    FakeErpnext,
    customer,
    error,
    sales_invoice,
    tax_template,
)
from tests.fakes.settings import DRAFTS_PER_HOUR
from tests.integration.clock import HOUR_AGO, TODAY
from tests.integration.mcp import Result, Session

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


def create(mcp: Session, **arguments: Any) -> Result:
    return mcp.call(
        "create_draft_sales_invoice", {"customer": "CUST-0001", "items": ONE_ITEM, **arguments}
    )


def update(mcp: Session, name: str = DRAFT, modified: str = MODIFIED, **arguments: Any) -> Result:
    return mcp.call("update_draft_sales_invoice", {"name": name, "modified": modified, **arguments})


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
    [post] = erp.writes(PATH)
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
    [post] = erp.writes(PATH)
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
        "tax_summary": [
            {
                "account_head": "1776 - VAT 19% - EX",
                "rate": 19.0,
                "taxable_amount": 125.0,
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
    [comment] = erp.comments  # the origin only (REQ-001-PRS-F015)
    assert "<br>" not in comment["content"]


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
    assert erp.writes() == []


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
    assert erp.writes() == []


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
    assert len(erp.writes(PATH)) == 1


@pytest.mark.parametrize(
    ("count", "more"), [(1, ""), (5, ""), (6, " and 1 more")], ids=["one", "five", "six"]
)
def test_a_refusal_names_up_to_five_drafts_and_counts_the_rest(
    mcp: Session, erp: FakeErpnext, count: int, more: str
) -> None:
    made = sorted(create(mcp, allow_duplicate=True).data["name"] for _ in range(count))
    again = create(mcp)
    assert again.error
    assert again.text == (
        "allow_duplicate: a draft with the same customer, posting date and items exists "
        f"({', '.join(made[:5])}{more}). Check it first; to create another anyway, repeat "
        "with allow_duplicate true."
    )
    assert len(erp.writes(PATH)) == count


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
    assert len(erp.writes(PATH)) == 2


def test_a_row_given_twice_counts_twice(mcp: Session, erp: FakeErpnext) -> None:
    row = {"item_code": "SKU-1", "qty": 1}
    first = create(mcp, items=[row, row]).data
    once = create(mcp, items=[row]).data
    assert once["warnings"] == []
    again = create(mcp, items=[row, row])
    assert again.error
    assert first["name"] in again.text
    assert once["name"] not in again.text
    assert len(erp.writes(PATH)) == 2


def test_a_draft_with_an_added_free_item_still_matches(mcp: Session, erp: FakeErpnext) -> None:
    erp.free_items["SKU-1"] = "GIFT"
    first = create(mcp).data
    again = create(mcp)
    assert again.error
    assert first["name"] in again.text


def test_a_duplicate_check_without_the_item_fields_is_refused(
    mcp: Session, erp: FakeErpnext
) -> None:
    # REQ-001-PRS-F018: with select only, the drafts arrive without their items and would
    # match nothing
    create(mcp)
    erp.select_only.add("Sales Invoice")
    again = create(mcp)
    assert again.error
    assert "Sales Invoice" in again.text
    assert "items.item_code" in again.text
    assert len(erp.writes(PATH)) == 1


def test_allow_duplicate_creates_and_leaves_the_warning_on_the_draft(
    mcp: Session, erp: FakeErpnext
) -> None:
    first = create(mcp).data
    second = create(mcp, allow_duplicate=True).data
    [warning] = second["warnings"]
    assert first["name"] in warning
    first_comment, comment = erp.comments
    assert first_comment["reference_name"] == first["name"]
    assert comment == {
        "reference_doctype": "Sales Invoice",
        "reference_name": second["name"],
        "content": comment["content"],
        "comment_email": "",
        "comment_by": "",
    }
    assert comment["content"].startswith("Enterich: create_draft_sales_invoice, call ")
    assert comment["content"].endswith(f"<br>{warning}")
    assert {r.method for r in erp.received if r.path == COMMENT_METHOD} == {"POST"}


# Warnings (REQ-001-PRS-F012, REQ-001-PRS-F015, REQ-001-PRS-F016, REQ-001-PRS-F020,
# REQ-001-PRS-F021)


def test_a_template_without_tax_warns_on_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, taxes_and_charges="VAT 0% - EX").data
    [warning] = result["warnings"]
    assert "VAT 0% - EX" in warning
    [comment] = erp.comments
    assert comment["content"].endswith(f"<br>{warning}")


ITEM_TAX: dict[str, float | str] = {"1776 - VAT 19% - EX": 19.0, "1777 - VAT 7% - EX": 0.0}
ITEM_TAX_WARNING = (
    "The draft has 2 tax rows, with 19.00 of tax, that ERPNext added from the items' item "
    "tax templates when it was saved without tax rows; check them in `taxes`, or give "
    "`taxes_and_charges` to replace them."
)
TAX_RULE_WARNING = (
    "ERPNext set the tax template VAT 19% - EX on the draft without its tax rows, as it does "
    "for a matching Tax Rule; give `taxes_and_charges` VAT 19% - EX to add them, or another "
    "template."
)


def test_rows_erpnext_added_from_item_tax_templates_warn(mcp: Session, erp: FakeErpnext) -> None:
    erp.item_taxes["SKU-1"] = ITEM_TAX
    result = create(mcp).data
    assert [(t["account_head"], t["rate"], t["tax_amount"]) for t in result["taxes"]] == [
        ("1776 - VAT 19% - EX", 0, 19),
        ("1777 - VAT 7% - EX", 0, 0),
    ]
    assert result["warnings"] == [ITEM_TAX_WARNING]


def test_one_row_erpnext_added_is_named_in_the_singular(mcp: Session, erp: FakeErpnext) -> None:
    erp.item_taxes["SKU-1"] = {"1776 - VAT 19% - EX": 19.0}
    [warning] = create(mcp).data["warnings"]
    assert warning.startswith("The draft has 1 tax row, with 19.00 of tax, that ERPNext ")


def test_a_given_template_takes_the_place_of_item_tax_rows(mcp: Session, erp: FakeErpnext) -> None:
    erp.item_taxes["SKU-1"] = ITEM_TAX
    result = create(mcp, taxes_and_charges="VAT 19% - EX").data
    assert [t["account_head"] for t in result["taxes"]] == ["1776 - VAT 19% - EX"]
    assert result["warnings"] == []


def test_clearing_the_template_warns_of_item_tax_rows(mcp: Session, erp: FakeErpnext) -> None:
    erp.item_taxes["SKU-1"] = ITEM_TAX
    result = update(mcp, taxes_and_charges="").data
    assert len(result["taxes"]) == 2
    # The fixture draft holds SKU-1 once, at 50
    assert result["warnings"] == [ITEM_TAX_WARNING.replace("19.00", "9.50")]


def test_item_tax_rows_warn_again_until_a_template_replaces_them(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.item_taxes["SKU-1"] = ITEM_TAX
    draft = create(mcp).data
    again = update(mcp, draft["name"], draft["modified"], remarks="Checked").data
    assert again["warnings"] == [ITEM_TAX_WARNING]
    replaced = update(mcp, draft["name"], again["modified"], taxes_and_charges="VAT 19% - EX").data
    assert replaced["warnings"] == []


def test_a_tax_rules_template_without_its_rows_warns(mcp: Session, erp: FakeErpnext) -> None:
    erp.tax_rules["CUST-0001"] = "VAT 19% - EX"
    result = create(mcp).data
    assert (result["taxes"], result["total_taxes_and_charges"]) == ([], 0)
    assert result["warnings"] == [TAX_RULE_WARNING]
    given = create(mcp, items=[{"item_code": "SKU-1", "qty": 3}], taxes_and_charges="VAT 19% - EX")
    assert given.data["warnings"] == []


def test_a_template_with_its_rows_doesnt_warn_on_update(mcp: Session, erp: FakeErpnext) -> None:
    erp.tax_rules["CUST-0001"] = "VAT 0% - EX"
    assert update(mcp, remarks="Checked").data["warnings"] == []


def test_a_rate_a_pricing_rule_replaced_warns(mcp: Session, erp: FakeErpnext) -> None:
    erp.rules["SKU-1"] = 45.0
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 2, "rate": 48}]).data
    assert result["items"][0]["rate"] == 45.0
    [warning] = result["warnings"]
    assert "row 1" in warning.lower()
    assert "SKU-1" in warning
    assert "48" in warning
    assert "45" in warning
    assert len(erp.comments) == 1


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
    # ERPNext answers 0 and 1; the result has booleans (REQ-001-PRS-F014)
    assert [type(r["is_free_item"]) for r in result["items"]] == [bool, bool]
    assert result["warnings"] == []
    assert [c["content"].count("<br>") for c in erp.comments] == [0]


def test_a_rate_erpnext_only_rounded_doesnt_warn(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 2, "rate": 12.346}]).data
    assert result["items"][0]["rate"] == 12.35
    assert result["warnings"] == []
    assert [c["content"].count("<br>") for c in erp.comments] == [0]


def test_the_warnings_go_on_the_draft_as_one_comment(mcp: Session, erp: FakeErpnext) -> None:
    items = [*ONE_ITEM, {"item_code": "SKU-9", "qty": 1}]
    result = create(mcp, items=items, taxes_and_charges="VAT 0% - EX").data
    tax, rate = result["warnings"]
    [comment] = erp.comments
    assert comment["content"].endswith(f"<br>{tax}<br>{rate}")


def test_markup_in_a_warning_reaches_erpnext_as_text(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "<img src=x onerror=alert(1)>", "qty": 1}]).data
    [warning] = result["warnings"]
    assert "<img src=x onerror=alert(1)>" in warning
    [comment] = erp.comments
    assert "<img" not in comment["content"]
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
    assert erp.comments == []


# Tax summary (REQ-001-PRS-F022)

TWO_RATES = [
    {**VAT_ROWS[0], "rate": 0.0},
    {**VAT_ROWS[0], "account_head": "1777 - VAT 7% - EX", "description": "VAT 7%", "rate": 0.0},
]


def summary(result: dict[str, Any]) -> list[tuple[str, float, float, float]]:
    return [
        (e["account_head"], e["rate"], e["taxable_amount"], e["tax_amount"])
        for e in result["tax_summary"]
    ]


def test_the_tax_summary_gives_each_rate_with_what_it_taxed(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Sales Taxes and Charges Template", tax_template("VAT 0/0 - EX", taxes=TWO_RATES))
    erp.item_taxes["SKU-1"] = {"1776 - VAT 19% - EX": 19.0, "1777 - VAT 7% - EX": "N/A"}
    erp.item_taxes["SKU-2"] = {"1776 - VAT 19% - EX": "N/A", "1777 - VAT 7% - EX": 7.0}
    items = [{"item_code": "SKU-1", "qty": 2}, {"item_code": "SKU-2", "qty": 1}]
    result = create(mcp, items=items, taxes_and_charges="VAT 0/0 - EX").data
    assert [t["rate"] for t in result["taxes"]] == [0, 0]
    assert summary(result) == [
        ("1776 - VAT 19% - EX", 19, 100, 19),
        ("1777 - VAT 7% - EX", 7, 20, 1.4),
    ]
    got = mcp.call("get_sales_invoice", {"name": result["name"]}).data
    assert got["tax_summary"] == result["tax_summary"]


def test_an_item_without_an_item_tax_template_is_in_it_at_0(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Sales Taxes and Charges Template", tax_template("VAT 0/0 - EX", taxes=TWO_RATES))
    erp.item_taxes["SKU-1"] = {"1776 - VAT 19% - EX": 19.0, "1777 - VAT 7% - EX": "N/A"}
    # SKU-3 at 10 twice: added up per row and rate, after the higher rate
    items = [{"item_code": c, "qty": 1} for c in ("SKU-3", "SKU-1", "SKU-3")]
    result = create(mcp, items=items, taxes_and_charges="VAT 0/0 - EX").data
    assert summary(result) == [
        ("1776 - VAT 19% - EX", 19, 50, 9.5),
        ("1776 - VAT 19% - EX", 0, 20, 0),
        ("1777 - VAT 7% - EX", 0, 20, 0),
    ]


def test_without_tax_rows_the_tax_summary_is_empty(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp).data
    assert (result["taxes"], result["tax_summary"]) == ([], [])


# The draft's origin (REQ-001-PRS-F015, REQ-002-PRS-NF008)


def test_a_create_leaves_its_origin_on_the_draft(
    mcp: Session, erp: FakeErpnext, logs: Logs
) -> None:
    result = create(mcp).data
    [line] = logs.events("operation")
    assert re.fullmatch(r"[0-9a-f]{12}", line["call"])
    assert line["request_id"] == str(mcp.request_id)
    [comment] = erp.comments
    assert (comment["reference_doctype"], comment["reference_name"]) == (
        "Sales Invoice",
        result["name"],
    )
    assert comment["content"] == f"Enterich: create_draft_sales_invoice, call {line['call']}."


def test_an_update_names_the_inputs_it_was_given(
    mcp: Session, erp: FakeErpnext, logs: Logs
) -> None:
    result = update(mcp, items=ONE_ITEM, remarks="")
    assert not result.error, result.text
    [line] = logs.events("operation")
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT
    assert comment["content"] == (
        f"Enterich: update_draft_sales_invoice, call {line['call']}; given items, remarks."
    )


def test_the_origin_comes_before_the_warnings(mcp: Session, erp: FakeErpnext, logs: Logs) -> None:
    result = create(mcp, taxes_and_charges="VAT 0% - EX").data
    [warning] = result["warnings"]
    [line] = logs.events("operation")
    [comment] = erp.comments
    assert comment["content"] == (
        f"Enterich: create_draft_sales_invoice, call {line['call']}.<br>{warning}"
    )


def test_each_operation_has_its_own_call(mcp: Session, logs: Logs) -> None:
    create(mcp)
    mcp.call("list_customers")
    first, second = logs.events("operation")
    assert first["call"] != second["call"]
    assert (first["request_id"], second["request_id"]) == (
        str(mcp.request_id - 1),
        str(mcp.request_id),
    )


def test_the_line_counts_the_erpnext_calls_and_their_time(
    mcp: Session, erp: FakeErpnext, logs: Logs
) -> None:
    erp.delay = 0.1
    create(mcp)
    assert [(r.method, r.path) for r in erp.received] == [
        ("GET", PATH),
        ("POST", PATH),
        ("POST", COMMENT_METHOD),
    ]
    [line] = logs.events("operation")
    assert line["erpnext_calls"] == 3
    assert 0.3 <= line["erpnext_duration"] <= line["duration"] < 1.0


def test_a_refused_write_leaves_no_comment(mcp: Session, erp: FakeErpnext, logs: Logs) -> None:
    assert create(mcp, customer="CUST-9999").error
    assert update(mcp, modified="2026-10-28 10:00:00.000000", remarks="x").error
    assert erp.comments == []
    assert all(re.fullmatch(r"[0-9a-f]{12}", line["call"]) for line in logs.events("operation"))


def test_a_failing_comment_without_warnings_still_says_so(mcp: Session, erp: FakeErpnext) -> None:
    erp.fail(COMMENT_METHOD, 403, error(403, "PermissionError", "Not permitted"))
    result = create(mcp).data
    assert result["name"] in erp.docs["Sales Invoice"]
    [missing] = result["warnings"]
    assert "comment" in missing


def test_the_comment_stays_within_the_operation_time(
    mcp: Session, erp: FakeErpnext, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "OPERATION_TIMEOUT", 1.0)
    erp.slow[COMMENT_METHOD] = 3.0
    started = time.monotonic()
    result = create(mcp).data
    assert time.monotonic() - started < 2.0
    assert result["name"] in erp.docs["Sales Invoice"]
    [missing] = result["warnings"]
    assert "comment" in missing


@pytest.mark.parametrize("name", ["enterich_request", "other"])
def test_an_argument_outside_the_schema_is_refused_whatever_its_name(
    mcp: Session, erp: FakeErpnext, logs: Logs, name: str
) -> None:
    result = create(mcp, **{name: "x"})
    assert result.error
    assert f"{name}: Extra inputs are not permitted" in result.text
    assert erp.writes() == []
    [line] = logs.events("operation")
    assert line["arguments"][name] == "x"


def test_a_long_request_id_is_cut_in_the_log(mcp: Session, logs: Logs) -> None:
    mcp.call("list_customers", request_id="r" * 10_000)
    [line] = logs.events("operation")
    assert line["request_id"] == "r" * 200


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
    [put] = erp.writes(PATH)
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
    [put] = erp.writes(PATH)
    assert put.body == {
        "taxes_and_charges": "VAT 19% - EX",
        "taxes": VAT_ROWS,
        "modified": MODIFIED,
    }


def test_clearing_the_template_clears_its_rows(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, taxes_and_charges="", remarks="").data
    [put] = erp.writes(PATH)
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
    assert erp.writes() == []


def test_a_draft_another_user_created_isnt_updated(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"][DRAFT]["owner"] = "bookkeeper@example.com"
    before = dict(erp.docs["Sales Invoice"][DRAFT])
    result = update(mcp, remarks="Changed")
    assert (result.error, result.text) == (
        True,
        f"name: {DRAFT} was created by another user; only drafts the agent user created can "
        "be updated.",
    )
    assert erp.writes() == []
    assert erp.docs["Sales Invoice"][DRAFT] == before


def test_the_agents_draft_a_person_edited_can_be_updated(mcp: Session, erp: FakeErpnext) -> None:
    edited = "2026-10-28 12:00:00.000000"
    erp.docs["Sales Invoice"][DRAFT].update(modified_by="bookkeeper@example.com", modified=edited)
    result = update(mcp, modified=edited, remarks="Checked")
    assert not result.error, result.text
    assert erp.docs["Sales Invoice"][DRAFT]["remarks"] == "Checked"


def test_the_agent_user_is_asked_for_once(mcp: Session, erp: FakeErpnext) -> None:
    first = update(mcp, remarks="First").data
    update(mcp, modified=first["modified"], remarks="Second")
    assert [r.path for r in erp.received].count(LOGGED_USER_METHOD) == 1


def test_creates_dont_ask_for_the_agent_user(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp)
    assert LOGGED_USER_METHOD not in [r.path for r in erp.received]


def test_an_update_without_the_agent_user_writes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    erp.fail(LOGGED_USER_METHOD, 500, error(500, "Exception", "Down"))
    refused = update(mcp, remarks="Changed")
    assert refused.error
    assert "500" in refused.text
    assert erp.writes() == []
    # A failed answer isn't kept: the next update asks again
    assert not update(mcp, remarks="Changed").error
    assert [r.path for r in erp.received].count(LOGGED_USER_METHOD) == 2


def test_another_users_draft_is_refused_before_its_modified_is_compared(
    mcp: Session, erp: FakeErpnext
) -> None:
    # A stale answer would send the agent to re-read and retry, which can't succeed
    erp.docs["Sales Invoice"][DRAFT]["owner"] = "bookkeeper@example.com"
    result = update(mcp, modified="2026-10-28 10:00:00.000000", remarks="Changed")
    assert result.error
    assert "created by another user" in result.text


@pytest.mark.parametrize("sent", ["2026-10-28 11:00:00", "2026-10-28 11:00:00.000000"])
def test_a_modified_on_a_whole_second_is_taken_as_erpnext_gives_it(
    mcp: Session, erp: FakeErpnext, sent: str
) -> None:
    erp.docs["Sales Invoice"][DRAFT]["modified"] = "2026-10-28 11:00:00"
    result = update(mcp, modified=sent, remarks="Checked")
    assert not result.error, result.text
    [put] = erp.writes(PATH)
    assert put.body["modified"] == sent


def test_a_stale_update_changes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    before = dict(erp.docs["Sales Invoice"][DRAFT])
    result = update(mcp, modified="2026-10-28 10:00:00.000000", remarks="Changed")
    assert result.error
    assert "changed" in result.text
    assert erp.writes() == []
    assert erp.docs["Sales Invoice"][DRAFT] == before


@pytest.mark.parametrize("stored", ["", None])
def test_a_draft_without_a_usable_modified_is_taken_as_changed(
    mcp: Session, erp: FakeErpnext, stored: str | None
) -> None:
    erp.docs["Sales Invoice"][DRAFT]["modified"] = stored
    result = update(mcp, remarks="Changed")
    assert result.error
    assert "changed" in result.text
    assert erp.writes() == []


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
    [put] = erp.writes(PATH)
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
    # Row 2 is matched to the second row given, not the first (REQ-001-PRS-F016)
    assert "19" in warning
    assert "15" in warning
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT


def test_an_update_to_a_template_without_tax_warns(mcp: Session) -> None:
    result = update(mcp, taxes_and_charges="VAT 0% - EX").data
    [warning] = result["warnings"]
    assert "VAT 0% - EX" in warning


def test_an_update_of_a_large_draft_cuts_its_rows(mcp: Session, erp: FakeErpnext) -> None:
    """REQ-001-PRS-NF003: items, taxes and the tax summary, each named in `truncated`."""
    rows = [invoice_row(f"SKU-{n % 3 + 1}", 1, 10.0) for n in range(150)]
    taxes = [
        {**VAT_ROWS[0], "name": f"tax-{n}", "account_head": f"1776-{n} - VAT 19% - EX"}
        for n in range(150)
    ]
    erp.docs["Sales Invoice"][DRAFT].update(items=rows, taxes=taxes)
    result = update(mcp, remarks="Checked").data
    tables = ["items", "taxes", "tax_summary"]
    assert [len(result[t]) for t in tables] == [100, 100, 100]
    assert result["truncated"] == tables
    assert len(erp.docs["Sales Invoice"][DRAFT]["items"]) == 150


def test_rows_at_rate_0_are_named_up_to_20(mcp: Session, erp: FakeErpnext) -> None:
    rows = [invoice_row(f"NP-{n}", 1, 0.0) for n in range(30)]
    erp.docs["Sales Invoice"][DRAFT]["items"] = rows
    result = update(mcp, remarks="Checked").data
    *named, more = result["warnings"]
    assert len(named) == 20
    assert "NP-19" in named[-1]
    assert "10 more rows" in more
    [comment] = erp.comments
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
    put = erp.writes(PATH)[-1]
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
    put = erp.writes(PATH)[-1]
    assert put.body == {"remarks": "Checked", "modified": created["modified"]}


def test_a_fixed_posting_date_keeps_the_due_date_on_a_later_day(
    mcp: Session, erp: FakeErpnext
) -> None:
    fixed = "2026-10-01"  # before TODAY; the terms of CUST-0001 would give 2026-10-31
    draft = sales_invoice(
        "ACC-SINV-2026-00021",
        docstatus=0,
        status="Draft",
        set_posting_time=1,
        posting_date=fixed,
        due_date="2026-10-20",
        payment_terms_template="",
        payment_schedule=[{"due_date": "2026-10-20", "invoice_portion": 100}],
        modified=MODIFIED,
    )
    erp.add("Sales Invoice", draft)
    result = update(mcp, "ACC-SINV-2026-00021", remarks="Checked")
    assert not result.error, result.text
    assert (result.data["posting_date"], result.data["due_date"]) == (fixed, "2026-10-20")
    put = erp.writes(PATH)[-1]
    assert put.body == {"remarks": "Checked", "modified": MODIFIED}


# Drafts per hour (REQ-001-PRS-F019)

LIMITED = (
    f"The agent user created {DRAFTS_PER_HOUR} sales invoices in the last hour, the most "
    "the operator allows (ENTERICH_MAX_DRAFTS_PER_HOUR); nothing was created. Try again "
    "later, or ask a person to review the drafts or to raise the limit."
)


def created(erp: FakeErpnext, name: str, creation: str, **overrides: Any) -> None:
    """A sales invoice made at `creation`, by the agent user unless `owner` says otherwise."""
    erp.add(
        "Sales Invoice", sales_invoice(name, **{"owner": AGENT, "creation": creation, **overrides})
    )


def test_at_the_limit_a_create_is_refused_without_a_write(
    limited: Session, erp: FakeErpnext
) -> None:
    created(erp, "ACC-SINV-2026-00030", "2026-10-29 01:00:00.000001", docstatus=0)
    created(erp, "ACC-SINV-2026-00031", "2026-10-29 01:59:59.000000")  # submitted since
    result = create(limited)
    assert result.error
    assert result.text == LIMITED
    assert erp.writes() == []


def test_a_document_older_than_an_hour_doesnt_count(limited: Session, erp: FakeErpnext) -> None:
    created(erp, "ACC-SINV-2026-00030", "2026-10-29 00:59:59.999999")
    created(erp, "ACC-SINV-2026-00031", "2026-10-29 01:30:00.000000")
    result = create(limited)
    assert not result.error, result.text


def test_another_users_or_companys_documents_dont_count(limited: Session, erp: FakeErpnext) -> None:
    created(erp, "ACC-SINV-2026-00030", "2026-10-29 01:30:00.000000")
    created(
        erp, "ACC-SINV-2026-00031", "2026-10-29 01:30:00.000000", owner="bookkeeper@example.com"
    )
    created(erp, "ACC-SINV-2026-00032", "2026-10-29 01:30:00.000000", company="Other AG")
    result = create(limited)
    assert not result.error, result.text


def test_the_count_sends_exactly_the_catalogued_call(limited: Session, erp: FakeErpnext) -> None:
    assert not create(limited).error
    count = erp.lists(PATH)[-1]
    assert count.param("fields") == ["name"]
    assert count.param("filters") == [
        ["company", "=", COMPANY],
        ["owner", "=", AGENT],
        ["creation", ">", HOUR_AGO],
    ]
    assert count.params["limit_page_length"] == str(DRAFTS_PER_HOUR)


def test_the_limit_counts_the_drafts_enterich_creates(limited: Session, erp: FakeErpnext) -> None:
    for qty in range(1, DRAFTS_PER_HOUR + 1):
        assert not create(limited, items=[{"item_code": "SKU-1", "qty": qty}]).error
    result = create(limited, items=[{"item_code": "SKU-1", "qty": 99}])
    assert result.text == LIMITED


def test_a_repeated_create_is_refused_as_a_duplicate_first(
    limited: Session, erp: FakeErpnext
) -> None:
    first = create(limited).data["name"]
    created(erp, "ACC-SINV-2026-00030", "2026-10-29 01:30:00.000000")
    result = create(limited)
    assert result.error
    assert result.text.startswith("allow_duplicate: ")
    assert first in result.text


def test_without_the_limit_a_create_makes_no_count(mcp: Session, erp: FakeErpnext) -> None:
    for name in ("ACC-SINV-2026-00030", "ACC-SINV-2026-00031", "ACC-SINV-2026-00032"):
        created(erp, name, "2026-10-29 01:30:00.000000")
    assert not create(mcp).error
    [duplicates] = erp.lists(PATH)
    assert "creation" not in duplicates.params["filters"]
