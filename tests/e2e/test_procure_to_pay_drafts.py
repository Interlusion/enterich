"""Purchase invoice drafts end to end (REQ-005-PRS-F005 to REQ-005-PRS-F007). REQ-001's
draft rules are tested through the sales drafts; these tests show the buying side's
bodies, its duplicate match by supplier invoice number, and its warnings."""

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest

from tests.e2e.clock import TIMEZONE, TODAY, freeze
from tests.e2e.mcp import Result, Session, client
from tests.fakes.erpnext import (
    COMPANY,
    STOCK_NOT_BILLED,
    TAXES_METHOD,
    FakeErpnext,
    Received,
    purchase_invoice,
    purchase_tax_template,
    supplier,
    tax_template,
)
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import settings

PATH = "/api/resource/Purchase Invoice"
DRAFT = "ACC-PINV-2026-00010"
MODIFIED = "2026-10-28 11:00:00.000000"
VAT_ROWS = [
    {
        "charge_type": "On Net Total",
        "account_head": "1576 - Input VAT 19% - EX",
        "add_deduct_tax": "Add",
        "category": "Total",
        "description": "Input VAT 19%",
        "rate": 19.0,
        "included_in_print_rate": 0,
        "cost_center": "Main - EX",
    }
]
ONE_ITEM = [{"item_code": "PAPER", "qty": 10, "rate": 20}]
DRAFT_ITEMS = [{"item_code": "PAPER", "qty": 5, "rate": 20}]  # the fixture draft's rows
COST = "5000 - Cost - EX"


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.today = TODAY
    erpnext.add("Supplier", supplier("SUPP-0001"))
    erpnext.add("Supplier", supplier("SUPP-0002"))
    erpnext.add("Purchase Taxes and Charges Template", purchase_tax_template())
    erpnext.add("Sales Taxes and Charges Template", tax_template("VAT 19% - EX"))
    erpnext.add("Purchase Invoice", purchase_invoice("ACC-PINV-2026-00001", bill_no="R-4711"))
    erpnext.add(
        "Purchase Invoice",
        purchase_invoice("ACC-PINV-2026-00002", bill_no="R-4712", docstatus=2, status="Cancelled"),
    )
    erpnext.add(
        "Purchase Invoice",
        purchase_invoice(
            DRAFT,
            bill_no="R-4800",
            bill_date="2026-10-27",
            due_date="2026-11-10",
            docstatus=0,
            status="Draft",
            set_posting_time=0,
            posting_date=TODAY,
            modified=MODIFIED,
            items=[{**purchase_invoice()["items"][0], "qty": 5.0, "amount": 100.0}],
        ),
    )
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext) -> Iterator[Session]:
    with client(jwks, settings(timezone=TIMEZONE), erp) as c:
        yield Session(c, token(signer))


def create(mcp: Session, **arguments: Any) -> Result:
    return mcp.call(
        "create_draft_purchase_invoice", {"supplier": "SUPP-0001", "items": ONE_ITEM, **arguments}
    )


def update(mcp: Session, name: str = DRAFT, modified: str = MODIFIED, **arguments: Any) -> Result:
    return mcp.call(
        "update_draft_purchase_invoice", {"name": name, "modified": modified, **arguments}
    )


def writes(erp: FakeErpnext) -> list[Received]:
    return [r for r in erp.received if r.method in ("POST", "PUT")]


def saves(erp: FakeErpnext) -> list[Received]:
    return [r for r in writes(erp) if r.path.startswith(PATH)]


def lists(erp: FakeErpnext) -> list[Received]:
    return [r for r in erp.received if r.method == "GET" and r.path == PATH]


# create_draft_purchase_invoice


def test_a_create_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    row = {
        "item_code": "PAPER",
        "qty": 10,
        "rate": 20,
        "uom": "Box",
        "expense_account": "4930 - Office - EX",
        "cost_center": "Main - EX",
    }
    result = create(
        mcp,
        bill_no="R-5000",
        bill_date="2026-10-25",
        posting_date="2026-11-02",
        due_date="2026-11-16",
        items=[row],
        taxes_and_charges="Input VAT 19% - EX",
        remarks="Office supplies",
    )
    assert not result.error, result.text
    [post] = saves(erp)
    assert (post.method, post.path) == ("POST", PATH)
    assert post.body == {
        "supplier": "SUPP-0001",
        "bill_no": "R-5000",
        "bill_date": "2026-10-25",
        "posting_date": "2026-11-02",
        "set_posting_time": 1,
        "due_date": "2026-11-16",
        "payment_terms_template": "",
        "items": [row],
        "taxes_and_charges": "Input VAT 19% - EX",
        "taxes": VAT_ROWS,
        "remarks": "Office supplies",
        "update_stock": 0,
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_create_without_optional_inputs_still_never_updates_stock(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = create(mcp)
    assert not result.error, result.text
    [post] = saves(erp)
    assert post.body == {
        "supplier": "SUPP-0001",
        "items": ONE_ITEM,
        "update_stock": 0,
        "company": COMPANY,
        "docstatus": 0,
    }


def test_the_template_rows_come_from_the_purchase_template(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp, taxes_and_charges="Input VAT 19% - EX")
    [taxes] = [r for r in erp.received if r.path == TAXES_METHOD]
    assert taxes.params == {
        "master_doctype": "Purchase Taxes and Charges Template",
        "master_name": "Input VAT 19% - EX",
    }


def test_a_sales_template_answers_as_unknown(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, taxes_and_charges="VAT 19% - EX")
    assert result.error
    assert result.text.startswith("taxes_and_charges:")
    assert writes(erp) == []


def test_a_create_returns_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, taxes_and_charges="Input VAT 19% - EX").data
    name = result["name"]
    assert name.startswith("ACC-PINV-")
    assert result == {
        "name": name,
        "modified": erp.docs["Purchase Invoice"][name]["modified"],
        "status": "Draft",
        "docstatus": 0,
        "company": COMPANY,
        "supplier": "SUPP-0001",
        "posting_date": TODAY,
        "due_date": str(date.fromisoformat(TODAY) + timedelta(days=14)),  # Net 14
        "currency": "EUR",
        "net_total": 200.0,
        "total_taxes_and_charges": 38.0,
        "grand_total": 238.0,
        "taxes": [
            {
                "account_head": "1576 - Input VAT 19% - EX",
                "rate": 19.0,
                "tax_amount": 38.0,
                "outside_text": {},
            }
        ],
        "items": [
            {
                "item_code": "PAPER",
                "qty": 10,
                "rate": 20,
                "amount": 200,
                "expense_account": COST,
                "is_free_item": False,
                "outside_text": {},
            }
        ],
        "url": f"https://erp.example.com/desk/purchase-invoice/{name}",
        "warnings": [],
        "truncated": [],
        "outside_text": {},
    }


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"items": [{"item_code": "PAPER", "qty": 10}]}, "rate"),
        ({"items": [{"item_code": "PAPER", "qty": 10, "rate": 0}]}, "rate"),
        ({"items": [{**ONE_ITEM[0], "income_account": COST}]}, "income_account"),
        ({"bill_no": ""}, "bill_no"),
        ({"bill_no": "R" * 141}, "bill_no"),
        ({"bill_no": " R-4711"}, "bill_no"),
        ({"bill_no": "R-4711 "}, "bill_no"),
        ({"bill_date": "28.10.2026"}, "bill_date"),
        ({"update_stock": 1}, "update_stock"),
        ({"customer": "CUST-0001"}, "customer"),
    ],
)
def test_inputs_outside_the_schema_are_refused_before_erpnext(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], named: str
) -> None:
    result = create(mcp, **arguments)
    assert result.error
    assert named in result.text
    assert erp.received == []


# Duplicates (REQ-005-PRS-F006)


def test_the_bill_check_sends_exactly_the_catalogued_call(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp, bill_no="R-9999")
    [check] = lists(erp)
    assert check.param("fields") == ["name"]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["supplier", "=", "SUPP-0001"],
        ["bill_no", "=", "R-9999"],
    ]


@pytest.mark.parametrize(
    ("bill_no", "found"), [("R-4711", "ACC-PINV-2026-00001"), ("R-4800", DRAFT)]
)
def test_a_recorded_supplier_invoice_is_refused_naming_it(
    mcp: Session, erp: FakeErpnext, bill_no: str, found: str
) -> None:
    result = create(mcp, bill_no=bill_no)
    assert result.error
    assert result.text.startswith("allow_duplicate:")
    assert found in result.text
    assert writes(erp) == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"bill_no": "R-4712"},  # only on a cancelled invoice
        {"bill_no": "R-4711", "supplier": "SUPP-0002"},
        {"bill_no": "R-6000", "items": DRAFT_ITEMS},  # a bill replaces the item match
    ],
)
def test_other_bills_go_through_without_warning(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any]
) -> None:
    result = create(mcp, **arguments)
    assert not result.error, result.text
    assert result.data["warnings"] == []


def test_allow_duplicate_records_the_bill_again_and_says_so(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, bill_no="R-4711", allow_duplicate=True).data
    [warning] = result["warnings"]
    assert "ACC-PINV-2026-00001" in warning
    assert len(erp.comments) == 1


def test_erpnexts_own_bill_check_still_refuses(mcp: Session, erp: FakeErpnext) -> None:
    erp.unique_bills = True
    result = create(mcp, bill_no="R-4711", allow_duplicate=True)
    assert result.error
    assert "Supplier Invoice No exists in Purchase Invoice ACC-PINV-2026-00001" in result.text


def test_without_a_bill_the_items_match(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=DRAFT_ITEMS)
    assert result.error
    assert DRAFT in result.text
    [check] = lists(erp)
    assert check.param("fields") == ["name", "items.item_code", "items.qty", "items.is_free_item"]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "=", 0],
        ["supplier", "=", "SUPP-0001"],
        ["posting_date", "=", TODAY],
    ]


# Warnings (REQ-005-PRS-F007, REQ-001-PRS-F016)


def test_a_replaced_expense_account_warns(mcp: Session, erp: FakeErpnext) -> None:
    erp.stock_items.add("PAPER")
    row = {**ONE_ITEM[0], "expense_account": "4930 - Office - EX"}
    result = create(mcp, bill_no="R-7000", items=[row]).data
    assert result["items"][0]["expense_account"] == STOCK_NOT_BILLED
    [warning] = result["warnings"]
    assert "row 1" in warning.lower()
    assert "PAPER" in warning
    assert "4930 - Office - EX" in warning
    assert STOCK_NOT_BILLED in warning
    [comment] = erp.comments
    assert comment["reference_doctype"] == "Purchase Invoice"


@pytest.mark.parametrize(
    ("stock", "row"),
    [
        (True, ONE_ITEM[0]),  # no account given
        (False, {**ONE_ITEM[0], "expense_account": "4930 - Office - EX"}),  # kept
    ],
)
def test_an_expense_account_not_given_or_kept_doesnt_warn(
    mcp: Session, erp: FakeErpnext, stock: bool, row: dict[str, Any]
) -> None:
    if stock:
        erp.stock_items.add("PAPER")
    result = create(mcp, bill_no="R-7000", items=[row]).data
    assert result["warnings"] == []
    assert erp.comments == []


def test_a_buying_pricing_rule_that_replaced_a_rate_warns(mcp: Session, erp: FakeErpnext) -> None:
    erp.rules["PAPER"] = 18.0
    result = create(mcp, bill_no="R-7000").data
    [warning] = result["warnings"]
    assert "20" in warning
    assert "18" in warning


# update_draft_purchase_invoice


def test_an_update_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    row = {"item_code": "PAPER", "qty": 12, "rate": 19, "expense_account": "4930 - Office - EX"}
    result = update(
        mcp,
        bill_no="R-4801",
        bill_date="2026-10-20",
        posting_date="2026-11-02",
        due_date="2026-11-30",
        items=[row],
        remarks="Corrected",
    )
    assert not result.error, result.text
    [put] = saves(erp)
    assert (put.method, put.path) == ("PUT", f"{PATH}/{DRAFT}")
    assert put.body == {
        "bill_no": "R-4801",
        "bill_date": "2026-10-20",
        "posting_date": "2026-11-02",
        "set_posting_time": 1,
        "due_date": "2026-11-30",
        "payment_terms_template": "",
        "payment_schedule": [],
        "items": [row],
        "remarks": "Corrected",
        "modified": MODIFIED,
    }


def test_an_update_with_a_template_sends_the_purchase_rows(mcp: Session, erp: FakeErpnext) -> None:
    update(mcp, taxes_and_charges="Input VAT 19% - EX")
    [put] = saves(erp)
    assert put.body == {
        "taxes_and_charges": "Input VAT 19% - EX",
        "taxes": VAT_ROWS,
        "modified": MODIFIED,
    }


def test_clearing_the_bill_number(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, bill_no="")
    assert not result.error, result.text
    [put] = saves(erp)
    assert put.body == {"bill_no": "", "modified": MODIFIED}
    assert erp.docs["Purchase Invoice"][DRAFT]["bill_no"] == ""


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"supplier": "SUPP-0002"}, "supplier"),
        ({"update_stock": 1}, "update_stock"),
        ({"items": [{"item_code": "PAPER", "qty": 1}]}, "rate"),
        ({}, "at least one"),
    ],
)
def test_an_update_refuses_what_it_doesnt_take(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], named: str
) -> None:
    result = update(mcp, **arguments)
    assert result.error
    assert named in result.text
    assert erp.received == []


def test_a_posting_date_set_by_an_update_is_kept(mcp: Session, erp: FakeErpnext) -> None:
    dated = update(mcp, posting_date="2026-11-02").data
    erp.today = "2026-10-30"
    later = update(mcp, modified=dated["modified"], remarks="Checked").data
    assert later["posting_date"] == "2026-11-02"


def test_only_drafts_can_be_updated(mcp: Session, erp: FakeErpnext) -> None:
    stored = erp.docs["Purchase Invoice"]["ACC-PINV-2026-00001"]
    result = update(mcp, "ACC-PINV-2026-00001", stored["modified"], remarks="Changed")
    assert result.error
    assert "submitted" in result.text
    assert writes(erp) == []


def test_a_stale_update_changes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, modified="2026-10-28 10:00:00.000000", remarks="Changed")
    assert result.error
    assert "changed" in result.text
    assert writes(erp) == []


def test_an_update_warns_where_an_expense_account_was_replaced(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.stock_items.add("PAPER")
    row = {**ONE_ITEM[0], "expense_account": "4930 - Office - EX"}
    result = update(mcp, items=[row]).data
    [warning] = result["warnings"]
    assert STOCK_NOT_BILLED in warning
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT


def test_an_update_of_the_bill_date_recounts_the_due_date(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, bill_date="2026-10-25").data
    assert result["due_date"] == "2026-11-08"  # Net 14 from the bill date
    [put] = saves(erp)
    assert put.body == {
        "bill_date": "2026-10-25",
        "payment_schedule": [],
        "due_date": None,
        "modified": MODIFIED,
    }


# Tax withholding


@pytest.mark.parametrize(
    "withholding", [{"tax_withholding_category": "TDS"}, {"tax_withholding_group": "Contractors"}]
)
def test_a_supplier_with_withholding_gets_it_applied(
    mcp: Session, erp: FakeErpnext, withholding: dict[str, str]
) -> None:
    erp.add("Supplier", supplier("SUPP-0003", **withholding))
    result = create(mcp, supplier="SUPP-0003")
    assert not result.error, result.text
    read = next(r for r in erp.received if r.path == "/api/method/frappe.client.get")
    assert read.params == {"doctype": "Supplier", "name": "SUPP-0003"}
    [post] = saves(erp)
    assert post.body["apply_tds"] == 1


def test_a_supplier_without_withholding_gets_none(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp, bill_no="R-7000")
    [post] = saves(erp)
    assert "apply_tds" not in post.body


def test_an_unknown_supplier_names_the_input(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, supplier="NOBODY")
    assert result.error
    assert result.text.startswith("supplier: ")
    assert writes(erp) == []


# The bill check on update (REQ-005-PRS-F006)


def test_an_update_to_a_recorded_bill_warns(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, bill_no="R-4711").data
    [warning] = result["warnings"]
    assert "ACC-PINV-2026-00001" in warning
    [check] = lists(erp)
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["supplier", "=", "SUPP-0001"],
        ["bill_no", "=", "R-4711"],
        ["name", "!=", DRAFT],
    ]
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT


def test_the_drafts_own_bill_doesnt_warn(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, bill_no="R-4800").data
    assert result["warnings"] == []
    cleared = update(mcp, modified=result["modified"], bill_no="").data
    assert cleared["warnings"] == []
    assert len(lists(erp)) == 1  # a cleared bill_no isn't checked


# Row warnings: per row, and accounts without regard to case


def test_the_cap_counts_rows_not_warnings(mcp: Session, erp: FakeErpnext) -> None:
    erp.rules["PAPER"] = 18.0
    erp.stock_items.add("PAPER")
    row = {**ONE_ITEM[0], "expense_account": "4930 - Office - EX"}
    result = create(mcp, bill_no="R-7000", items=[row] * 15).data
    assert len(result["warnings"]) == 30
    assert not any("more rows" in w for w in result["warnings"])


def test_an_account_in_another_case_doesnt_warn(mcp: Session, erp: FakeErpnext) -> None:
    row = {**ONE_ITEM[0], "expense_account": "4930 - office - ex"}
    result = create(mcp, bill_no="R-7000", items=[row]).data
    assert result["items"][0]["expense_account"] == "4930 - Office - EX"
    assert result["warnings"] == []


# The item match without a bill


@pytest.mark.parametrize(
    "arguments",
    [
        {"items": [{**DRAFT_ITEMS[0], "qty": 6}]},
        {"items": [{**DRAFT_ITEMS[0], "item_code": "TONER"}]},
        {"items": DRAFT_ITEMS, "posting_date": "2026-10-30"},
    ],
)
def test_a_create_differing_from_the_draft_goes_through(
    mcp: Session, arguments: dict[str, Any]
) -> None:
    result = create(mcp, **arguments)
    assert not result.error, result.text
    assert result.data["warnings"] == []


def test_allow_duplicate_on_the_item_match_warns(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=DRAFT_ITEMS, allow_duplicate=True).data
    [warning] = result["warnings"]
    assert DRAFT in warning
    assert len(erp.comments) == 1


def test_a_bill_older_than_its_terms_needs_its_due_date(mcp: Session) -> None:
    # v16 counts the due date from the bill date but never before the posting date, and
    # then refuses it as later than the terms allow.
    old = create(mcp, bill_no="R-3000", bill_date="2026-09-01")
    assert old.error
    assert "Due Date cannot be after" in old.text
    given = create(mcp, bill_no="R-3000", bill_date="2026-09-01", due_date="2026-09-15")
    assert not given.error, given.text
    assert given.data["due_date"] == "2026-09-15"
