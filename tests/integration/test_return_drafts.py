"""Return drafts: credit notes against sales invoices and debit notes against purchase
invoices, built from ERPNext's return of the invoice (REQ-004-PRS-F007,
REQ-004-PRS-F008, REQ-005-PRS-F008, REQ-005-PRS-F009)."""

from typing import Any, cast

import pytest

from tests.fakes.erpnext import (
    AGENT,
    COMPANY,
    DEBIT_NOTE_METHOD,
    SALES_RETURN_METHOD,
    FakeErpnext,
    customer,
    purchase_invoice,
    sales_invoice,
    supplier,
)
from tests.fakes.settings import DRAFTS_PER_HOUR
from tests.integration.clock import TODAY
from tests.integration.mcp import Result, Session

SALES = "/api/resource/Sales Invoice"
PURCHASES = "/api/resource/Purchase Invoice"
INVOICE = "ACC-SINV-2026-00001"  # SKU-1 on rows r1 (3, one returned) and r3 (2); SKU-2 returned
BILL = "ACC-PINV-2026-00001"  # SKU-1 on row p1 (2)
SALES_DRAFT = "ACC-SINV-2026-00020"  # the agent's draft return against INVOICE
PURCHASE_DRAFT = "ACC-PINV-2026-00020"  # the agent's draft return against BILL
MODIFIED = "2026-10-28 11:00:00.000000"


def row(name: str, code: str, qty: float, rate: float, doctype: str) -> dict[str, Any]:
    return {
        "doctype": f"{doctype} Item",
        "name": name,
        "item_code": code,
        "qty": qty,
        "rate": rate,
        "amount": qty * rate,
        "uom": "Nos",
        "conversion_factor": 1.0,
        "stock_qty": qty,
    }


def returned(
    name: str, against: str, link: str, rows: list[tuple[str, str, float]], **fields: Any
) -> dict[str, Any]:
    """A return against `against`, its rows (invoice row, item, quantity returned)."""
    return {
        "is_return": 1,
        "return_against": against,
        "posting_date": "2026-10-20",
        "status": "Return",
        "grand_total": -50.0,
        "outstanding_amount": -50.0,
        "items": [
            {"item_code": code, "qty": -qty, "rate": 50.0, link: line} for line, code, qty in rows
        ],
        **fields,
    }


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.today = TODAY
    erpnext.add("Customer", customer("CUST-0001"))
    erpnext.add("Supplier", supplier("SUPP-0001"))
    lines = [
        row("r1", "SKU-1", 3.0, 50.0, "Sales Invoice"),
        row("r2", "SKU-2", 1.0, 20.0, "Sales Invoice"),
        row("r3", "SKU-1", 2.0, 50.0, "Sales Invoice"),
    ]
    erpnext.add("Sales Invoice", sales_invoice(INVOICE, items=lines))
    erpnext.add(
        "Sales Invoice",
        sales_invoice(
            "ACC-SINV-2026-00002",
            **returned(
                "ACC-SINV-2026-00002",
                INVOICE,
                "sales_invoice_item",
                [("r1", "SKU-1", 1.0), ("r2", "SKU-2", 1.0)],
            ),
        ),
    )
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00003", docstatus=0, status="Draft"))
    erpnext.add(
        "Sales Invoice", sales_invoice("ACC-SINV-2026-00004", docstatus=2, status="Cancelled")
    )
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00005", is_pos=1))
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00006", update_stock=1))
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00007", company="Other AG"))
    erpnext.add(
        "Sales Invoice",
        sales_invoice(
            SALES_DRAFT,
            **returned(
                SALES_DRAFT,
                INVOICE,
                "sales_invoice_item",
                [("r3", "SKU-1", 1.0)],
                docstatus=0,
                status="Draft",
                modified=MODIFIED,
            ),
        ),
    )
    bill_rows = [row("p1", "SKU-1", 2.0, 40.0, "Purchase Invoice")]
    erpnext.add("Purchase Invoice", purchase_invoice(BILL, items=bill_rows))
    erpnext.add("Purchase Invoice", purchase_invoice("ACC-PINV-2026-00002", update_stock=1))
    erpnext.add("Purchase Invoice", purchase_invoice("ACC-PINV-2026-00003", is_paid=1))
    erpnext.add(
        "Purchase Invoice",
        purchase_invoice(
            PURCHASE_DRAFT,
            **returned(
                PURCHASE_DRAFT,
                BILL,
                "purchase_invoice_item",
                [("p1", "SKU-1", 1.0)],
                docstatus=0,
                status="Draft",
                modified=MODIFIED,
            ),
        ),
    )
    return erpnext


def stripped(value: Any) -> Any:
    """A mapped return as the catalogue sends it: without `name`, `owner` and the fields
    starting with `__`, in its rows too."""
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        return {
            k: stripped(v)
            for k, v in mapping.items()
            if k not in ("name", "owner") and not k.startswith("__")
        }
    if isinstance(value, list):
        return [stripped(v) for v in cast("list[Any]", value)]
    return value


def lines(mapped: dict[str, Any], *taken: tuple[int, float]) -> list[dict[str, Any]]:
    """The mapped return's rows `taken` (index, quantity returned), as Enterich sends them:
    a debit note's row received in full, nothing rejected."""
    rows = stripped(mapped["items"])
    sent = [{**rows[i], "qty": -qty, "stock_qty": -qty} for i, qty in taken]
    for line in sent:
        if "received_qty" in line:
            line.update(received_qty=line["qty"], rejected_qty=0)
    return sent


def invoice(
    erp: FakeErpnext, doctype: str, name: str, rows: list[tuple[str, str, float]], **fields: Any
) -> None:
    """A submitted invoice of CUST-0001 or SUPP-0001, its rows (name, item, quantity) at 50."""
    factory = sales_invoice if doctype == "Sales Invoice" else purchase_invoice
    items = [row(line, code, qty, 50.0, doctype) for line, code, qty in rows]
    erp.add(doctype, factory(name, items=items, **fields))


def tool(doctype: str, kind: str = "create") -> str:
    return f"{kind}_draft_{'sales' if doctype == 'Sales Invoice' else 'purchase'}_return"


def numbered(doctype: str, number: int) -> str:
    return f"ACC-{'SINV' if doctype == 'Sales Invoice' else 'PINV'}-2026-{number:05d}"


SIDES = ["Sales Invoice", "Purchase Invoice"]


def create(mcp: Session, tool: str = "create_draft_sales_return", **arguments: Any) -> Result:
    against = INVOICE if tool == "create_draft_sales_return" else BILL
    return mcp.call(tool, {"return_against": against, **arguments})


def update(mcp: Session, tool: str = "update_draft_sales_return", **arguments: Any) -> Result:
    draft = SALES_DRAFT if tool == "update_draft_sales_return" else PURCHASE_DRAFT
    return mcp.call(tool, {"name": draft, "modified": MODIFIED, **arguments})


# create_draft_sales_return (REQ-004-PRS-F007)


def test_a_create_sends_erpnexts_return_with_the_given_items(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    mapped = erp.mapped_return("Sales Invoice", INVOICE)
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 3}], posting_date="2026-10-27")
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    assert post.body == {
        **stripped(mapped),
        # SKU-1 has 2 left on r1 and 2 on r3: taken in row order
        "items": lines(mapped, (0, 2), (2, 1)),
        "posting_date": "2026-10-27",
        "set_posting_time": 1,
        "company": COMPANY,
        "docstatus": 0,
    }
    [mapping] = [r for r in erp.received if r.path == SALES_RETURN_METHOD]
    assert (mapping.method, mapping.params) == ("GET", {"source_name": INVOICE})


def test_a_create_with_items_leaves_out_the_other_items(mcp: Session, erp: FakeErpnext) -> None:
    invoice(
        erp, "Sales Invoice", "ACC-SINV-2026-00008", [("v1", "SKU-1", 2.0), ("v2", "SKU-2", 1.0)]
    )
    mapped = erp.mapped_return("Sales Invoice", "ACC-SINV-2026-00008")
    result = mcp.call(
        "create_draft_sales_return",
        {"return_against": "ACC-SINV-2026-00008", "items": [{"item_code": "SKU-1", "qty": 1}]},
    )
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    # SKU-2 on v2 has 1 left to return, and isn't given
    assert post.body["items"] == lines(mapped, (0, 1))


def test_a_create_without_items_returns_all_that_is_left(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    mapped = erp.mapped_return("Sales Invoice", INVOICE)
    result = create(mcp, remarks="Damaged in transit")
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    # SKU-2 on r2 is returned already
    assert post.body["items"] == lines(mapped, (0, 2), (2, 2))
    assert (post.body["posting_date"], post.body["set_posting_time"]) == (TODAY, 1)
    assert post.body["remarks"] == "Damaged in transit"


def test_a_create_returns_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 1}]).data
    assert result["return_against"] == INVOICE
    assert (result["customer"], result["docstatus"], result["status"]) == ("CUST-0001", 0, "Draft")
    assert result["net_total"] == -50
    assert [(r["item_code"], r["qty"]) for r in result["items"]] == [("SKU-1", -1)]
    # Negative, as the return's tax rows (REQ-001-PRS-F022)
    assert [(e["taxable_amount"], e["tax_amount"]) for e in result["tax_summary"]] == [(-50, -9.5)]
    assert result["url"].endswith(f"/desk/sales-invoice/{result['name']}")
    assert result["warnings"] == []


def test_the_return_tools_carry_their_annotations_and_say_how_to_retry(mcp: Session) -> None:
    tools = {t["name"]: t for t in mcp.tools()}
    for side in ("sales", "purchase"):
        created, updated = (
            tools[f"create_draft_{side}_return"],
            tools[f"update_draft_{side}_return"],
        )
        assert created["annotations"]["destructiveHint"] is False
        assert updated["annotations"]["idempotentHint"] is True
        assert "state` draft" in created["description"]


@pytest.mark.parametrize(
    ("invoice", "says"),
    [
        ("ACC-SINV-2026-00003", "a draft"),
        ("ACC-SINV-2026-00004", "cancelled"),
        ("ACC-SINV-2026-00002", f"a return itself; give the invoice it returns ({INVOICE})."),
        ("ACC-SINV-2026-00005", "POS"),
        ("ACC-SINV-2026-00006", "stock"),
        ("ACC-SINV-2026-00007", "doesn't exist"),
        ("ACC-SINV-2026-09999", "doesn't exist"),
    ],
)
def test_only_a_submitted_invoice_of_the_company_takes_a_return(
    mcp: Session, erp: FakeErpnext, invoice: str, says: str
) -> None:
    result = mcp.call("create_draft_sales_return", {"return_against": invoice})
    assert result.error
    assert result.text.startswith("return_against: ")
    assert invoice in result.text
    assert says in result.text
    assert erp.writes() == []
    assert [r for r in erp.received if r.path == SALES_RETURN_METHOD] == []


@pytest.mark.parametrize(
    ("items", "says"),
    [
        ([{"item_code": "SKU-9", "qty": 1}], "SKU-9 isn't on"),
        ([{"item_code": "SKU-1", "qty": 5}], "5 of SKU-1 can't be returned; 4 left"),
        ([{"item_code": "SKU-2", "qty": 1}], "1 of SKU-2 can't be returned; 0 left"),
        ([{"item_code": "SKU-1", "qty": 1}] * 2, "once"),
    ],
)
def test_items_are_returned_at_most_as_far_as_left(
    mcp: Session, erp: FakeErpnext, items: list[dict[str, Any]], says: str
) -> None:
    result = create(mcp, items=items)
    assert result.error
    assert result.text.startswith("items: ")
    assert says in result.text
    assert erp.writes() == []


def test_an_invoice_with_nothing_left_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"]["ACC-SINV-2026-00002"]["items"] += [
        {"item_code": "SKU-1", "qty": -2.0, "rate": 50.0, "sales_invoice_item": "r1"},
        {"item_code": "SKU-1", "qty": -2.0, "rate": 50.0, "sales_invoice_item": "r3"},
    ]
    result = create(mcp)
    assert result.error
    assert result.text.startswith("return_against: ")
    assert "nothing left" in result.text
    assert erp.writes() == []


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"items": [{"item_code": "SKU-1", "qty": 0}]}, "items.0.qty: "),
        ({"items": [{"item_code": "SKU-1", "qty": -1}]}, "items.0.qty: "),
        ({"items": [{"item_code": "SKU-1", "qty": 1.0001}]}, "items.0.qty: "),
        ({"items": []}, "items: "),
        ({"items": [{"item_code": "SKU-1", "qty": 1}] * 21}, "items: "),
        ({"items": [{"item_code": "SKU-1", "qty": 1, "rate": 60}]}, "items.0.rate: Extra"),
        ({"customer": "CUST-0002"}, "customer: Extra inputs are not permitted"),
        ({"is_return": 0}, "is_return: Extra inputs are not permitted"),
        ({"bill_no": "CN-1"}, "bill_no: Extra inputs are not permitted"),
    ],
)
def test_inputs_outside_the_schema_are_refused(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = create(mcp, **arguments)
    assert result.error
    assert says in result.text
    assert erp.received == []


# Duplicates (REQ-004-PRS-F008)


def test_a_draft_return_against_the_invoice_is_a_duplicate(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 1}])
    assert result.error
    assert result.text.startswith("allow_duplicate: ")
    assert SALES_DRAFT in result.text
    assert erp.writes() == []
    [check] = [r for r in erp.lists(SALES) if ["is_return", "=", 1] in r.param("filters")]
    assert check.param("fields") == ["name"]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "=", 0],
        ["is_return", "=", 1],
        ["return_against", "=", INVOICE],
    ]
    assert check.params["order_by"] == "name asc"


def test_submitted_and_cancelled_returns_arent_duplicates(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"][SALES_DRAFT].update(docstatus=2, status="Cancelled")
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 1}])
    assert not result.error, result.text
    assert result.data["warnings"] == []


def test_allow_duplicate_creates_and_warns(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 1}], allow_duplicate=True)
    [warning] = result.data["warnings"]
    assert SALES_DRAFT in warning
    assert len(erp.comments) == 1


def test_a_return_counts_with_the_sales_invoices(limited: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    for number in range(DRAFTS_PER_HOUR):
        erp.add(
            "Sales Invoice",
            sales_invoice(f"ACC-SINV-2026-0009{number}", docstatus=0, creation=erp.now),
        )
    result = create(limited, items=[{"item_code": "SKU-1", "qty": 1}])
    assert result.error
    assert "sales invoices in the last hour" in result.text
    assert erp.writes() == []


# create_draft_purchase_return (REQ-005-PRS-F008)


def test_a_debit_note_sends_erpnexts_return_with_the_credit_notes_number(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    mapped = erp.mapped_return("Purchase Invoice", BILL)
    result = create(
        mcp,
        "create_draft_purchase_return",
        items=[{"item_code": "SKU-1", "qty": 1}],
        bill_no="CN-77",
        bill_date="2026-10-25",
    )
    assert not result.error, result.text
    [post] = erp.writes(PURCHASES)
    assert post.body == {
        **stripped(mapped),
        "items": lines(mapped, (0, 1)),
        "bill_no": "CN-77",
        "bill_date": "2026-10-25",
        "posting_date": TODAY,
        "set_posting_time": 1,
        "company": COMPANY,
        "docstatus": 0,
    }
    [mapping] = [r for r in erp.received if r.path == DEBIT_NOTE_METHOD]
    assert mapping.params == {"source_name": BILL}
    data = result.data
    assert (data["return_against"], data["supplier"]) == (BILL, "SUPP-0001")
    assert data["outside_text"] == {"bill_no": "CN-77"}  # the supplier's text


def test_a_debit_note_sends_the_given_posting_date_and_remarks_with_the_number(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    mapped = erp.mapped_return("Purchase Invoice", BILL)
    result = create(
        mcp,
        "create_draft_purchase_return",
        items=[{"item_code": "SKU-1", "qty": 1}],
        bill_no="CN-77",
        bill_date="2026-10-25",
        posting_date="2026-10-27",
        remarks="Damaged",
    )
    assert not result.error, result.text
    [post] = erp.writes(PURCHASES)
    assert post.body == {
        **stripped(mapped),
        "items": lines(mapped, (0, 1)),
        "bill_no": "CN-77",
        "bill_date": "2026-10-25",
        "posting_date": "2026-10-27",
        "set_posting_time": 1,
        "remarks": "Damaged",
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_debit_note_without_a_number_keeps_the_invoices(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    result = create(mcp, "create_draft_purchase_return")
    assert not result.error, result.text
    [post] = erp.writes(PURCHASES)
    assert post.body["bill_no"] == "R-4711"
    assert post.body["items"][0]["qty"] == -2


@pytest.mark.parametrize(
    ("invoice", "says"),
    [("ACC-PINV-2026-00002", "stock"), ("ACC-PINV-2026-00003", "paid")],
)
def test_a_purchase_invoice_that_updated_stock_or_was_paid_takes_no_return(
    mcp: Session, erp: FakeErpnext, invoice: str, says: str
) -> None:
    result = mcp.call("create_draft_purchase_return", {"return_against": invoice})
    assert result.error
    assert result.text.startswith("return_against: ")
    assert says in result.text
    assert erp.writes() == []


def test_a_draft_debit_note_against_the_invoice_is_a_duplicate(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = create(mcp, "create_draft_purchase_return")
    assert result.error
    assert result.text.startswith("allow_duplicate: ")
    assert PURCHASE_DRAFT in result.text


# update_draft_sales_return, update_draft_purchase_return


@pytest.mark.parametrize("doctype", SIDES)
def test_an_update_with_items_sends_the_rows_of_erpnexts_return(
    mcp: Session, erp: FakeErpnext, doctype: str
) -> None:
    against = INVOICE if doctype == "Sales Invoice" else BILL
    method = SALES_RETURN_METHOD if doctype == "Sales Invoice" else DEBIT_NOTE_METHOD
    mapped = erp.mapped_return(doctype, against)
    result = update(mcp, tool(doctype, "update"), items=[{"item_code": "SKU-1", "qty": 2}])
    assert not result.error, result.text
    [put] = erp.writes(f"/api/resource/{doctype}")
    assert (put.method, put.path) == ("PUT", f"/api/resource/{doctype}/{numbered(doctype, 20)}")
    assert put.body == {"items": lines(mapped, (0, 2)), "modified": MODIFIED}
    [mapping] = [r for r in erp.received if r.path == method]
    assert mapping.params == {"source_name": against}
    assert [(r["item_code"], r["qty"]) for r in result.data["items"]] == [("SKU-1", -2)]


@pytest.mark.parametrize("doctype", SIDES)
def test_an_update_without_items_sends_no_rows(
    mcp: Session, erp: FakeErpnext, doctype: str
) -> None:
    result = update(mcp, tool(doctype, "update"), posting_date="2026-10-27", remarks="")
    assert not result.error, result.text
    [put] = erp.writes(f"/api/resource/{doctype}")
    assert put.body == {
        "posting_date": "2026-10-27",
        "set_posting_time": 1,
        "remarks": "",
        "modified": MODIFIED,
    }
    methods = (SALES_RETURN_METHOD, DEBIT_NOTE_METHOD)
    assert [r for r in erp.received if r.path in methods] == []


def test_an_update_of_a_debit_note_sends_the_credit_notes_number(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = update(mcp, "update_draft_purchase_return", bill_no="CN-78", bill_date="2026-10-26")
    assert not result.error, result.text
    [put] = erp.writes(PURCHASES)
    assert put.body == {"bill_no": "CN-78", "bill_date": "2026-10-26", "modified": MODIFIED}
    assert result.data["outside_text"] == {"bill_no": "CN-78"}  # the supplier's text


@pytest.mark.parametrize("kind", ["create", "update"])
def test_a_debit_note_returns_what_a_purchase_invoice_draft_does(
    mcp: Session, erp: FakeErpnext, kind: str
) -> None:
    for doc in erp.docs["Purchase Invoice"].values():
        for line in doc["items"]:
            line["expense_account"] = "5000 - Cost - EX"
    if kind == "create":
        erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
        result = create(
            mcp, "create_draft_purchase_return", items=[{"item_code": "SKU-1", "qty": 1}]
        )
    else:
        result = update(mcp, "update_draft_purchase_return", remarks="Damaged")
    assert not result.error, result.text
    assert [(r["item_code"], r["expense_account"]) for r in result.data["items"]] == [
        ("SKU-1", "5000 - Cost - EX")
    ]
    assert [
        (t["account_head"], t["add_deduct_tax"], t["category"]) for t in result.data["taxes"]
    ] == [("1576 - Input VAT 19% - EX", "Add", "Total")]


def test_an_update_without_a_change_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp)
    assert result.error
    assert "give at least one of items, posting_date, remarks" in result.text
    assert erp.received == []


def test_an_update_beyond_what_is_left_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, items=[{"item_code": "SKU-1", "qty": 5}])
    assert result.error
    assert result.text.startswith("items: ")
    assert "5 of SKU-1 can't be returned; 4 left" in result.text
    assert erp.writes() == []


@pytest.mark.parametrize(
    ("tool", "draft", "names"),
    [
        ("update_draft_sales_invoice", SALES_DRAFT, "update_draft_sales_return"),
        ("update_draft_purchase_invoice", PURCHASE_DRAFT, "update_draft_purchase_return"),
    ],
)
def test_the_invoice_updates_refuse_a_return(
    mcp: Session, erp: FakeErpnext, tool: str, draft: str, names: str
) -> None:
    result = mcp.call(tool, {"name": draft, "modified": MODIFIED, "remarks": "Changed"})
    assert result.error
    assert result.text.startswith("name: ")
    assert names in result.text
    assert erp.writes() == []


@pytest.mark.parametrize(
    ("tool", "doctype", "invoice", "names"),
    [
        (
            "update_draft_sales_return",
            "Sales Invoice",
            "ACC-SINV-2026-00030",
            "update_draft_sales_invoice",
        ),
        (
            "update_draft_purchase_return",
            "Purchase Invoice",
            "ACC-PINV-2026-00030",
            "update_draft_purchase_invoice",
        ),
    ],
)
def test_the_return_updates_refuse_an_invoice(
    mcp: Session, erp: FakeErpnext, tool: str, doctype: str, invoice: str, names: str
) -> None:
    factory = sales_invoice if doctype == "Sales Invoice" else purchase_invoice
    erp.add(doctype, factory(invoice, docstatus=0, status="Draft", modified=MODIFIED))
    result = mcp.call(tool, {"name": invoice, "modified": MODIFIED, "remarks": "Changed"})
    assert result.error
    assert result.text.startswith("name: ")
    assert names in result.text
    assert erp.writes() == []


def test_a_return_another_user_created_isnt_updated(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"][SALES_DRAFT]["owner"] = "someone@example.com"
    result = update(mcp, remarks="Changed")
    assert result.error
    assert "created by another user" in result.text
    assert erp.writes() == []
    assert erp.docs["Sales Invoice"][SALES_DRAFT]["owner"] != AGENT


# What is left, and from which rows (REQ-004-PRS-F007, REQ-005-PRS-F008)


def test_a_free_item_row_is_taken_after_the_paid_one(mcp: Session, erp: FakeErpnext) -> None:
    invoice(
        erp, "Sales Invoice", "ACC-SINV-2026-00008", [("f1", "SKU-1", 1.0), ("f2", "SKU-1", 2.0)]
    )
    erp.docs["Sales Invoice"]["ACC-SINV-2026-00008"]["items"][0].update(rate=0.0, is_free_item=1)
    result = mcp.call(
        "create_draft_sales_return",
        {"return_against": "ACC-SINV-2026-00008", "items": [{"item_code": "SKU-1", "qty": 1}]},
    )
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    assert [(r["sales_invoice_item"], r["qty"]) for r in post.body["items"]] == [("f2", -1)]


@pytest.mark.parametrize("items", [[{"item_code": "SKU-1", "qty": 0.2}], None])
def test_what_is_left_carries_no_binary_residue(
    mcp: Session, erp: FakeErpnext, items: list[dict[str, Any]] | None
) -> None:
    invoice(erp, "Sales Invoice", "ACC-SINV-2026-00008", [("q1", "SKU-1", 0.3)])
    erp.add(
        "Sales Invoice",
        sales_invoice(
            "ACC-SINV-2026-00009",
            **returned(
                "ACC-SINV-2026-00009",
                "ACC-SINV-2026-00008",
                "sales_invoice_item",
                [("q1", "SKU-1", 0.1)],
            ),
        ),
    )
    given = {"items": items} if items else {}
    result = mcp.call(
        "create_draft_sales_return", {"return_against": "ACC-SINV-2026-00008", **given}
    )
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    assert [(r["qty"], r["stock_qty"]) for r in post.body["items"]] == [(-0.2, -0.2)]


def test_a_debit_note_row_is_received_as_returned(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    result = create(mcp, "create_draft_purchase_return", items=[{"item_code": "SKU-1", "qty": 1}])
    assert not result.error, result.text
    [post] = erp.writes(PURCHASES)
    [line] = post.body["items"]
    assert (line["qty"], line["received_qty"], line["stock_qty"], line["rejected_qty"]) == (
        -1,
        -1,
        -1,
        0,
    )


@pytest.mark.parametrize("doctype", SIDES)
@pytest.mark.parametrize(("factor", "stock_qty"), [(12.0, -12), (None, -1)], ids=["box", "none"])
def test_a_rows_stock_quantity_is_what_is_taken_in_the_stock_uom(
    mcp: Session, erp: FakeErpnext, doctype: str, factor: float | None, stock_qty: float
) -> None:
    name = numbered(doctype, 8)
    invoice(erp, doctype, name, [("u1", "SKU-1", 2.0)])
    [line] = erp.docs[doctype][name]["items"]
    del line["conversion_factor"]
    if factor:
        line.update(uom="Box", conversion_factor=factor, stock_qty=2.0 * factor)
    result = mcp.call(
        tool(doctype), {"return_against": name, "items": [{"item_code": "SKU-1", "qty": 1}]}
    )
    assert not result.error, result.text
    [post] = erp.writes(f"/api/resource/{doctype}")
    assert [(r["qty"], r["stock_qty"]) for r in post.body["items"]] == [(-1, stock_qty)]


# Fixed discounts and charges


ACTUAL = {"charge_type": "Actual", "account_head": "Freight - EX", "rate": 0.0, "tax_amount": 20.0}


@pytest.mark.parametrize("doctype", SIDES)
@pytest.mark.parametrize(
    "fixed",
    [{"discount_amount": 10.0}, {"taxes": [ACTUAL]}],
    ids=["discount", "charge"],
)
def test_an_invoice_with_a_fixed_amount_is_returned_only_whole(
    mcp: Session, erp: FakeErpnext, doctype: str, fixed: dict[str, Any]
) -> None:
    name = numbered(doctype, 8)
    invoice(erp, doctype, name, [("w1", "SKU-1", 2.0), ("w2", "SKU-2", 1.0)], **fixed)
    part = mcp.call(
        tool(doctype), {"return_against": name, "items": [{"item_code": "SKU-1", "qty": 2}]}
    )
    assert part.error
    assert part.text.startswith("items: ")
    assert name in part.text
    assert "fixed" in part.text
    assert erp.writes() == []
    every = [{"item_code": "SKU-1", "qty": 2}, {"item_code": "SKU-2", "qty": 1}]
    whole = mcp.call(tool(doctype), {"return_against": name, "items": every})
    assert not whole.error, whole.text
    erp.docs[doctype].pop(whole.data["name"])
    assert not mcp.call(tool(doctype), {"return_against": name}).error


@pytest.mark.parametrize("doctype", SIDES)
@pytest.mark.parametrize(
    "fixed",
    [{"discount_amount": 10.0}, {"taxes": [ACTUAL]}],
    ids=["discount", "charge"],
)
@pytest.mark.parametrize("items", [None, [{"item_code": "SKU-1", "qty": 2}]], ids=["all", "some"])
def test_a_partly_returned_invoice_with_a_fixed_amount_takes_no_return(
    mcp: Session,
    erp: FakeErpnext,
    doctype: str,
    fixed: dict[str, Any],
    items: list[dict[str, Any]] | None,
) -> None:
    name = numbered(doctype, 8)
    invoice(erp, doctype, name, [("w1", "SKU-1", 2.0), ("w2", "SKU-2", 1.0)], **fixed)
    link = "sales_invoice_item" if doctype == "Sales Invoice" else "purchase_invoice_item"
    factory = sales_invoice if doctype == "Sales Invoice" else purchase_invoice
    back = numbered(doctype, 9)
    erp.add(doctype, factory(back, **returned(back, name, link, [("w2", "SKU-2", 1.0)])))
    arguments: dict[str, Any] = {"return_against": name}
    if items is not None:
        arguments["items"] = items
    result = mcp.call(tool(doctype), arguments)
    assert result.error
    assert result.text.startswith(f"return_against: {name} ")
    assert "fixed" in result.text
    assert erp.writes() == []


@pytest.mark.parametrize("doctype", SIDES)
@pytest.mark.parametrize(
    ("taken", "says", "not_says"),
    [(1.0, "fixed", "nothing left"), (2.0, "nothing left", "fixed")],
    ids=["one-left", "none-left"],
)
def test_a_returned_invoice_with_a_fixed_amount_is_refused_down_to_its_last_unit(
    mcp: Session, erp: FakeErpnext, doctype: str, taken: float, says: str, not_says: str
) -> None:
    name, before = numbered(doctype, 8), numbered(doctype, 9)
    invoice(erp, doctype, name, [("x1", "SKU-1", 2.0)], discount_amount=10.0)
    link = "sales_invoice_item" if doctype == "Sales Invoice" else "purchase_invoice_item"
    factory = sales_invoice if doctype == "Sales Invoice" else purchase_invoice
    erp.add(doctype, factory(before, **returned(before, name, link, [("x1", "SKU-1", taken)])))
    result = mcp.call(tool(doctype), {"return_against": name})
    assert result.error
    assert result.text.startswith(f"return_against: {name} ")
    assert says in result.text
    assert not_says not in result.text
    assert erp.writes() == []


def test_a_discount_given_as_a_percentage_is_returned_in_part(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    erp.docs["Sales Invoice"][INVOICE].update(
        discount_amount=27.0, additional_discount_percentage=10
    )
    result = create(mcp, items=[{"item_code": "SKU-1", "qty": 1}])
    assert not result.error, result.text


# Posting time


@pytest.mark.parametrize("doctype", SIDES)
def test_a_return_dated_the_invoices_day_carries_its_posting_time(
    mcp: Session, erp: FakeErpnext, doctype: str
) -> None:
    name = numbered(doctype, 8)
    invoice(erp, doctype, name, [("t1", "SKU-1", 2.0)], posting_date=TODAY, posting_time="09:30:00")
    result = mcp.call(tool(doctype), {"return_against": name})
    assert not result.error, result.text
    [post] = erp.writes(f"/api/resource/{doctype}")
    assert (post.body["posting_date"], post.body["posting_time"]) == (TODAY, "09:30:00")


def test_a_return_dated_later_keeps_the_mapped_posting_time(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Sales Invoice"].pop(SALES_DRAFT)
    erp.docs["Sales Invoice"][INVOICE]["posting_time"] = "09:30:00"
    result = create(mcp)
    assert not result.error, result.text
    [post] = erp.writes(SALES)
    assert post.body["posting_time"] == erp.mapped_return("Sales Invoice", INVOICE)["posting_time"]


def test_an_update_to_the_invoices_day_carries_its_posting_time(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Sales Invoice"][INVOICE]["posting_time"] = "09:30:00"
    result = update(mcp, posting_date="2026-10-01")
    assert not result.error, result.text
    [put] = erp.writes(SALES)
    assert put.body == {
        "posting_date": "2026-10-01",
        "set_posting_time": 1,
        "posting_time": "09:30:00",
        "modified": MODIFIED,
    }


# Updates check the invoice again


@pytest.mark.parametrize("doctype", SIDES)
@pytest.mark.parametrize(
    "change", [{"items": [{"item_code": "SKU-1", "qty": 1}]}, {"posting_date": "2026-10-27"}]
)
@pytest.mark.parametrize(
    ("invoice_fields", "says"),
    [
        ({"docstatus": 2, "status": "Cancelled"}, "cancelled"),
        ({"company": "Other AG"}, "doesn't exist"),
    ],
)
def test_an_update_refuses_an_invoice_a_create_refuses(
    mcp: Session,
    erp: FakeErpnext,
    doctype: str,
    change: dict[str, Any],
    invoice_fields: dict[str, Any],
    says: str,
) -> None:
    sales = doctype == "Sales Invoice"
    erp.docs[doctype][INVOICE if sales else BILL].update(invoice_fields)
    result = update(mcp, tool(doctype, "update"), **change)
    assert result.error
    assert result.text.startswith("return_against: ")
    assert says in result.text
    assert erp.writes() == []
    method = SALES_RETURN_METHOD if sales else DEBIT_NOTE_METHOD
    assert [r for r in erp.received if r.path == method] == []


@pytest.mark.parametrize("doctype", SIDES)
def test_a_return_against_no_invoice_isnt_updated(
    mcp: Session, erp: FakeErpnext, doctype: str
) -> None:
    draft = SALES_DRAFT if doctype == "Sales Invoice" else PURCHASE_DRAFT
    erp.docs[doctype][draft]["return_against"] = None
    result = update(mcp, tool(doctype, "update"), remarks="Changed")
    assert result.error
    assert result.text.startswith("name: ")
    assert "against no invoice" in result.text
    assert erp.writes() == []


def test_a_return_without_its_invoice_is_refused_without_naming_none(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00008", is_return=1, return_against=None, status="Return"),
    )
    result = mcp.call("create_draft_sales_return", {"return_against": "ACC-SINV-2026-00008"})
    assert result.error
    assert "a return itself" in result.text
    assert "None" not in result.text


# The purchase side's refusals (REQ-005-PRS-F008)


@pytest.mark.parametrize(
    ("invoice_fields", "says"),
    [
        ({"docstatus": 0, "status": "Draft"}, "a draft"),
        ({"docstatus": 2, "status": "Cancelled"}, "cancelled"),
        (
            {"is_return": 1, "return_against": "ACC-PINV-2026-00002"},
            "a return itself; give the invoice it returns (ACC-PINV-2026-00002).",
        ),
        ({"company": "Other AG"}, "doesn't exist"),
        ({"on_hold": 1, "release_date": "2026-11-30"}, "on hold"),
    ],
)
def test_only_a_submitted_purchase_invoice_of_the_company_takes_a_return(
    mcp: Session, erp: FakeErpnext, invoice_fields: dict[str, Any], says: str
) -> None:
    erp.add("Purchase Invoice", purchase_invoice("ACC-PINV-2026-00008", **invoice_fields))
    result = mcp.call("create_draft_purchase_return", {"return_against": "ACC-PINV-2026-00008"})
    assert result.error
    assert result.text.startswith("return_against: ")
    assert "ACC-PINV-2026-00008" in result.text
    assert says in result.text
    assert erp.writes() == []
    assert [r for r in erp.received if r.path == DEBIT_NOTE_METHOD] == []


@pytest.mark.parametrize("kind", ["create", "update"])
@pytest.mark.parametrize(
    ("items", "says"),
    [
        ([{"item_code": "SKU-9", "qty": 1}], "SKU-9 isn't on"),
        ([{"item_code": "SKU-1", "qty": 3}], "3 of SKU-1 can't be returned; 2 left"),
    ],
)
def test_a_debit_note_returns_items_at_most_as_far_as_left(
    mcp: Session, erp: FakeErpnext, kind: str, items: list[dict[str, Any]], says: str
) -> None:
    if kind == "create":
        erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
        result = create(mcp, "create_draft_purchase_return", items=items)
    else:
        result = update(mcp, "update_draft_purchase_return", items=items)
    assert result.error
    assert result.text.startswith("items: ")
    assert says in result.text
    assert BILL in result.text
    assert erp.writes() == []


def test_a_purchase_invoice_with_nothing_left_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Purchase Invoice"][PURCHASE_DRAFT].update(docstatus=1, status="Return")
    erp.docs["Purchase Invoice"][PURCHASE_DRAFT]["items"][0]["qty"] = -2.0
    result = create(mcp, "create_draft_purchase_return")
    assert result.error
    assert result.text.startswith("return_against: ")
    assert "nothing left" in result.text
    assert erp.writes() == []


# A debit note's credit note number (REQ-005-PRS-F009)


def credit_note(erp: FakeErpnext, **fields: Any) -> None:
    """A draft invoice of SUPP-0001 with the credit note number CN-77."""
    erp.add(
        "Purchase Invoice",
        purchase_invoice("ACC-PINV-2026-00009", bill_no="CN-77", docstatus=0, **fields),
    )


def test_a_debit_note_with_a_known_number_is_a_duplicate(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    credit_note(erp, status="Draft")
    result = create(
        mcp,
        "create_draft_purchase_return",
        items=[{"item_code": "SKU-1", "qty": 1}],
        bill_no="CN-77",
    )
    assert result.error
    assert result.text.startswith("allow_duplicate: ")
    assert "ACC-PINV-2026-00009" in result.text
    assert "bill_no" in result.text
    assert erp.writes() == []
    [check] = [r for r in erp.lists(PURCHASES) if ["bill_no", "=", "CN-77"] in r.param("filters")]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["supplier", "=", "SUPP-0001"],
        ["bill_no", "=", "CN-77"],
    ]


def test_a_debit_note_with_a_known_number_is_created_when_allowed(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Purchase Invoice"].pop(PURCHASE_DRAFT)
    credit_note(erp, status="Draft")
    result = create(
        mcp,
        "create_draft_purchase_return",
        items=[{"item_code": "SKU-1", "qty": 1}],
        bill_no="CN-77",
        allow_duplicate=True,
    )
    assert not result.error, result.text
    [warning] = result.data["warnings"]
    assert "ACC-PINV-2026-00009" in warning


def test_a_debit_note_update_with_a_known_number_warns(mcp: Session, erp: FakeErpnext) -> None:
    credit_note(erp, status="Draft")
    result = update(mcp, "update_draft_purchase_return", bill_no="CN-77")
    assert not result.error, result.text
    [warning] = result.data["warnings"]
    assert "ACC-PINV-2026-00009" in warning


def test_a_debit_notes_own_number_doesnt_warn(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Purchase Invoice"][PURCHASE_DRAFT]["bill_no"] = "CN-80"
    result = update(mcp, "update_draft_purchase_return", bill_no="CN-80")
    assert not result.error, result.text
    assert result.data["warnings"] == []
    [check] = [r for r in erp.lists(PURCHASES) if ["bill_no", "=", "CN-80"] in r.param("filters")]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["supplier", "=", "SUPP-0001"],
        ["bill_no", "=", "CN-80"],
        ["name", "!=", PURCHASE_DRAFT],
    ]


def test_an_empty_bill_no_clears_a_debit_notes_number(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, "update_draft_purchase_return", bill_no="")
    assert not result.error, result.text
    [put] = erp.writes(PURCHASES)
    assert put.body == {"bill_no": "", "modified": MODIFIED}
    assert [r for r in erp.lists(PURCHASES) if ["bill_no", "=", ""] in r.param("filters")] == []
