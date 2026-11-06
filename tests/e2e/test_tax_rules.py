"""A Tax Rule's template on a draft made through the API: ERPNext sets it as
`taxes_and_charges` without its rows, and Enterich warns (REQ-001-PRS-F021)."""

from collections.abc import Iterator

import pytest

from tests.e2e.seed import COMPANY, Seed
from tests.e2e.site import Site
from tests.integration.mcp import Session


@pytest.fixture
def tax_rules(site: Site, seeded: Seed) -> Iterator[None]:
    """A sales Tax Rule for the customer and a purchase one for the supplier, with the
    seeded templates, for one test; removed afterwards."""
    rules = [
        site.insert(
            {
                "doctype": "Tax Rule",
                "company": COMPANY,
                "tax_type": "Sales",
                "customer": seeded.customer,
                "sales_tax_template": seeded.sales_template,
                "use_for_shopping_cart": 0,
            }
        )["name"],
        site.insert(
            {
                "doctype": "Tax Rule",
                "company": COMPANY,
                "tax_type": "Purchase",
                "supplier": seeded.supplier,
                "purchase_tax_template": seeded.purchase_template,
                "use_for_shopping_cart": 0,
            }
        )["name"],
    ]
    try:
        yield
    finally:
        for name in rules:
            site.delete("Tax Rule", name)


def warning(template: str) -> str:
    return (
        f"ERPNext set the tax template {template} on the draft without its tax rows, as it "
        f"does for a matching Tax Rule; give `taxes_and_charges` {template} to add them, or "
        "another template."
    )


def test_a_tax_rules_sales_template_comes_without_its_rows(
    tax_rules: None, mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": [{"item_code": seeded.item, "qty": 23}]},
    ).data
    assert (draft["taxes"], draft["total_taxes_and_charges"]) == ([], 0)
    assert draft["warnings"] == [warning(seeded.sales_template)]
    doc = site.call("frappe.client.get", doctype="Sales Invoice", name=draft["name"])
    assert (doc["taxes_and_charges"], doc["taxes"]) == (seeded.sales_template, [])


def test_a_tax_rules_purchase_template_comes_without_its_rows(
    tax_rules: None, mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_purchase_invoice",
        {
            "supplier": seeded.supplier,
            "bill_no": "E2E-RULE-1",
            "items": [{"item_code": seeded.item, "qty": 1, "rate": 23}],
        },
    ).data
    assert draft["taxes"] == []
    assert draft["warnings"] == [warning(seeded.purchase_template)]
    doc = site.call("frappe.client.get", doctype="Purchase Invoice", name=draft["name"])
    assert doc["taxes_and_charges"] == seeded.purchase_template
