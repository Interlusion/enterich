"""Both sides of invoicing against the seeded site: parties with their addresses, invoices
with their rows, tax templates, and the aged reports with the catalogues' filters and
columns (REQ-004-PRS-F001 to REQ-004-PRS-F004, REQ-005-PRS-F001 to REQ-005-PRS-F004)."""

from datetime import timedelta

from tests.e2e.seed import INPUT_VAT, SALES_VAT, Seed, site_today
from tests.integration.mcp import Session


def test_list_customers(mcp: Session, seeded: Seed) -> None:
    records = mcp.call("list_customers", {"search": "Example"}).data["records"]
    customers = {r["name"]: r for r in records}
    assert customers[seeded.customer]["customer_type"] == "Company"


def test_get_customer_with_its_address(mcp: Session, seeded: Seed) -> None:
    customer = mcp.call("get_customer", {"name": seeded.customer}).data
    assert customer["name"] == seeded.customer
    [address] = customer["addresses"]
    assert (address["name"], address["address_type"], address["country"]) == (
        seeded.customer_address,
        "Billing",
        "Germany",
    )
    assert address["outside_text"]["city"] == "Example City"


def test_get_supplier_with_its_address(mcp: Session, seeded: Seed) -> None:
    supplier = mcp.call("get_supplier", {"name": seeded.supplier}).data
    assert supplier["name"] == seeded.supplier
    assert [a["name"] for a in supplier["addresses"]] == [seeded.supplier_address]


def test_list_suppliers(mcp: Session, seeded: Seed) -> None:
    records = mcp.call("list_suppliers", {"search": "Example"}).data["records"]
    assert seeded.supplier in [r["name"] for r in records]


def test_list_sales_invoices_with_every_filter(mcp: Session, seeded: Seed) -> None:
    day = seeded.posted.isoformat()
    records = mcp.call(
        "list_sales_invoices",
        {"customer": seeded.customer, "state": "unpaid", "from_date": day, "to_date": day},
    ).data["records"]
    assert [r["name"] for r in records] == [seeded.sales_invoice]
    invoice = records[0]
    assert (invoice["net_total"], invoice["grand_total"], invoice["outstanding_amount"]) == (
        100,
        119,
        69,
    )
    assert (invoice["status"], invoice["docstatus"]) == ("Partly Paid", 1)


def test_a_partly_paid_sales_invoice_is_in_no_other_state(mcp: Session, seeded: Seed) -> None:
    states = ["paid", "draft", "return", "cancelled"]
    # Overdue once its due date has passed, on a site kept that long
    if site_today() <= seeded.sales_due:
        states.append("overdue")
    for state in states:
        records = mcp.call(
            "list_sales_invoices", {"customer": seeded.customer, "state": state}
        ).data["records"]
        assert seeded.sales_invoice not in [r["name"] for r in records], state


def test_get_sales_invoice_with_its_rows(mcp: Session, seeded: Seed) -> None:
    invoice = mcp.call("get_sales_invoice", {"name": seeded.sales_invoice}).data
    assert invoice["taxes_and_charges"] == seeded.sales_template
    assert [(r["item_code"], r["qty"], r["rate"], r["amount"]) for r in invoice["items"]] == [
        (seeded.item, 2, 50, 100)
    ]
    assert invoice["items"][0]["income_account"] == "4110 - Sales - EX"
    assert [(t["account_head"], t["rate"], t["tax_amount"]) for t in invoice["taxes"]] == [
        (SALES_VAT[1], 19, 19)
    ]


def test_get_purchase_invoice_with_its_rows(mcp: Session, seeded: Seed) -> None:
    invoice = mcp.call("get_purchase_invoice", {"name": seeded.purchase_invoice}).data
    assert (invoice["supplier"], invoice["grand_total"], invoice["status"]) == (
        seeded.supplier,
        47.6,
        "Unpaid",
    )
    assert invoice["outside_text"]["bill_no"] == "SEED-BILL-1"
    assert [
        (t["account_head"], t["add_deduct_tax"], t["tax_amount"]) for t in invoice["taxes"]
    ] == [(INPUT_VAT[1], "Add", 7.6)]


def test_list_purchase_invoices(mcp: Session, seeded: Seed) -> None:
    records = mcp.call(
        "list_purchase_invoices", {"supplier": seeded.supplier, "state": "unpaid"}
    ).data["records"]
    assert [(r["name"], r["bill_date"]) for r in records] == [
        (seeded.purchase_invoice, seeded.posted.isoformat())
    ]


def test_tax_templates_of_both_sides(mcp: Session, seeded: Seed) -> None:
    sales = mcp.call("list_sales_tax_templates", {"limit": 50}).data["records"]
    purchase = mcp.call("list_purchase_tax_templates", {"limit": 50}).data["records"]
    assert seeded.sales_template in [t["name"] for t in sales]
    assert seeded.purchase_template in [t["name"] for t in purchase]
    # The setup wizard's default for each side
    assert [t["name"] for t in sales if t["is_default"]] == [
        "Lieferung oder sonstige Leistung im Inland - EX"
    ]
    assert [t["name"] for t in purchase if t["is_default"]] == ["Lieferung aus dem Inland - EX"]


def test_accounts_receivable_ages_the_open_part_by_due_date(mcp: Session, seeded: Seed) -> None:
    report = mcp.call(
        "report_accounts_receivable",
        {"customer": seeded.customer, "as_of_date": seeded.posted.isoformat()},
    ).data
    [record] = report["records"]
    assert (record["voucher_type"], record["voucher_no"], record["party"]) == (
        "Sales Invoice",
        seeded.sales_invoice,
        seeded.customer,
    )
    assert (record["invoiced"], record["paid"], record["credit_note"], record["outstanding"]) == (
        119,
        50,
        0,
        69,
    )
    assert (record["due_date"], record["currency"]) == (seeded.sales_due.isoformat(), "EUR")
    # Not yet due on the day it was posted
    assert record["ageing"] == {
        "range0": 69,
        **dict.fromkeys(("range1", "range2", "range3", "range4", "range5"), 0),
    }
    assert report["total_outstanding"] == 69


def test_accounts_receivable_as_of_today_by_default(mcp: Session, seeded: Seed) -> None:
    report = mcp.call("report_accounts_receivable", {"customer": seeded.customer}).data
    [record] = report["records"]
    assert (record["voucher_no"], record["outstanding"]) == (seeded.sales_invoice, 69)
    assert sum(record["ageing"].values()) == 69
    assert report["total_outstanding"] == 69


def test_accounts_payable_by_posting_date(mcp: Session, seeded: Seed) -> None:
    report = mcp.call(
        "report_accounts_payable",
        {
            "supplier": seeded.supplier,
            "ageing_based_on": "posting_date",
            "as_of_date": seeded.posted.isoformat(),
        },
    ).data
    [record] = report["records"]
    assert (record["voucher_no"], record["bill_date"], record["outstanding"]) == (
        seeded.purchase_invoice,
        seeded.posted.isoformat(),
        47.6,
    )
    assert record["outside_text"] == {"bill_no": "SEED-BILL-1"}
    # By posting date nothing is "not yet due": 0 days old falls in 0-30
    assert record["ageing"] == {
        "range0": 0,
        "range1": 47.6,
        **dict.fromkeys(("range2", "range3", "range4", "range5"), 0),
    }
    assert report["total_outstanding"] == 47.6


def test_accounts_receivable_as_of_the_day_before_shows_nothing(mcp: Session, seeded: Seed) -> None:
    day = (seeded.posted - timedelta(days=1)).isoformat()
    report = mcp.call(
        "report_accounts_receivable", {"customer": seeded.customer, "as_of_date": day}
    ).data
    assert (report["records"], report["total_outstanding"]) == ([], 0)
