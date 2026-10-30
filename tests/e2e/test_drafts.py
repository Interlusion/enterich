"""The drafts against the seeded site: create and update as the agent user, the warnings
as a comment on the draft, and the duplicate check with drafts and invoices people made
(REQ-001 Drafts, REQ-004-PRS-F005, REQ-004-PRS-F006, REQ-005-PRS-F005 to
REQ-005-PRS-F007, REQ-006-PRS-F005 to REQ-006-PRS-F008).

The seed removes earlier runs' drafts; within a run, each test uses its own quantities
or amounts, so no test's draft is another's duplicate by party, date and items or rows.
By bill_no they are: two tests make drafts with the seeded purchase invoice's, which the
duplicate check finds too, so those tests expect the seeded invoice first, not alone."""

from typing import Any

from tests.e2e.seed import AGENT, CAPITAL, COMPANY, SALES_VAT, Seed, site_today
from tests.e2e.site import Site
from tests.integration.mcp import Session

# The setup wizard's default sales template: its rates are 0 % and come from item tax
# templates, which the seeded items don't have.
ZERO_TEMPLATE = "Lieferung oder sonstige Leistung im Inland - EX"


def comments(site: Site, doctype: str, name: str) -> list[dict[str, Any]]:
    return site.get_list(
        "Comment",
        {"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
        ["content", "owner"],
    )


def stored(site: Site, doctype: str, name: str) -> dict[str, Any]:
    return site.call("frappe.client.get", doctype=doctype, name=name)


# Sales invoices


def test_create_draft_sales_invoice(mcp: Session, seeded: Seed, site: Site) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {
            "customer": seeded.customer,
            "items": [{"item_code": seeded.item, "qty": 1, "rate": 50}],
            "taxes_and_charges": seeded.sales_template,
            "remarks": "Agent's draft",
        },
    ).data
    assert (draft["status"], draft["docstatus"], draft["company"]) == ("Draft", 0, COMPANY)
    assert (draft["posting_date"], draft["net_total"]) == (site_today().isoformat(), 50)
    assert (draft["total_taxes_and_charges"], draft["grand_total"]) == (9.5, 59.5)
    assert [(t["account_head"], t["tax_amount"]) for t in draft["taxes"]] == [(SALES_VAT[1], 9.5)]
    assert draft["warnings"] == []
    doc = stored(site, "Sales Invoice", draft["name"])
    assert (doc["owner"], doc["remarks"]) == (AGENT, "Agent's draft")
    assert comments(site, "Sales Invoice", draft["name"]) == []


def test_the_warnings_go_on_the_draft_as_one_comment(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {
            "customer": seeded.customer,
            "items": [{"item_code": seeded.unpriced_item, "qty": 2}],
            "taxes_and_charges": ZERO_TEMPLATE,
        },
    ).data
    assert draft["warnings"] == [
        f"Tax template {ZERO_TEMPLATE} was given, but the tax total is 0; check the template "
        "and the items' tax templates.",
        f"Row 1 ({seeded.unpriced_item}) was saved at rate 0: the price list has no price for "
        "the item. Give the rate.",
    ]
    [comment] = comments(site, "Sales Invoice", draft["name"])
    assert comment["owner"] == AGENT
    assert comment["content"] == "Enterich: " + "<br>".join(draft["warnings"])


def test_a_persons_sales_draft_is_a_duplicate(mcp: Session, seeded: Seed, site: Site) -> None:
    items = [{"item_code": seeded.item, "qty": 3, "rate": 10}]
    theirs = site.insert(
        {
            "doctype": "Sales Invoice",
            "company": COMPANY,
            "customer": seeded.customer,
            "posting_date": site_today().isoformat(),
            "set_posting_time": 1,
            "items": items,
        }
    )["name"]
    inputs = {"customer": seeded.customer, "items": items}
    refused = mcp.call("create_draft_sales_invoice", inputs)
    assert refused.error
    assert refused.text.startswith(
        f"allow_duplicate: a draft with the same customer, posting date and items exists "
        f"({theirs})."
    )
    draft = mcp.call("create_draft_sales_invoice", {**inputs, "allow_duplicate": True}).data
    assert draft["warnings"] == [
        f"Possible duplicate of {theirs}: a draft with the same customer, posting date and items."
    ]


def test_update_draft_sales_invoice(mcp: Session, seeded: Seed, site: Site) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": [{"item_code": seeded.item, "qty": 4, "rate": 10}]},
    ).data
    updated = mcp.call(
        "update_draft_sales_invoice",
        {
            "name": draft["name"],
            "modified": draft["modified"],
            "items": [{"item_code": seeded.item, "qty": 5, "rate": 12}],
            "taxes_and_charges": seeded.sales_template,
        },
    ).data
    assert (updated["net_total"], updated["grand_total"]) == (60, 71.4)
    assert updated["modified"] != draft["modified"]
    doc = stored(site, "Sales Invoice", draft["name"])
    assert [(r["qty"], r["rate"]) for r in doc["items"]] == [(5, 12)]
    assert doc["taxes_and_charges"] == seeded.sales_template
    # The draft as first read is stale now
    stale = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": draft["modified"], "remarks": "Too late"},
    )
    assert (stale.error, stale.text) == (
        True,
        "modified: the draft has changed since it was read; get it again and repeat the "
        "update with its new `modified`.",
    )


def test_a_submitted_sales_invoice_isnt_updated(mcp: Session, seeded: Seed) -> None:
    invoice = mcp.call("get_sales_invoice", {"name": seeded.sales_invoice}).data
    refused = mcp.call(
        "update_draft_sales_invoice",
        {"name": seeded.sales_invoice, "modified": invoice["modified"], "remarks": "Changed"},
    )
    assert (refused.error, refused.text) == (
        True,
        f"name: {seeded.sales_invoice} is submitted; only drafts can be updated.",
    )


# Purchase invoices


def test_a_submitted_purchase_invoice_with_the_bill_no_is_a_duplicate(
    mcp: Session, seeded: Seed
) -> None:
    inputs = {
        "supplier": seeded.supplier,
        "bill_no": "SEED-BILL-1",
        "items": [{"item_code": seeded.item, "qty": 6, "rate": 5}],
    }
    refused = mcp.call("create_draft_purchase_invoice", inputs)
    assert refused.error
    assert refused.text.startswith(
        "allow_duplicate: a purchase invoice with the same supplier and bill_no exists "
        f"({seeded.purchase_invoice}"
    )
    draft = mcp.call("create_draft_purchase_invoice", {**inputs, "allow_duplicate": True}).data
    [warning] = draft["warnings"]
    assert warning.startswith(f"Possible duplicate of {seeded.purchase_invoice}")
    assert warning.endswith(": a purchase invoice with the same supplier and bill_no.")


def test_an_expense_account_erpnext_replaced_is_a_warning(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    # A stock item bought without updating stock is booked on Stock Received But Not Billed
    given = "5111 - Cost of Goods Sold - EX"
    draft = mcp.call(
        "create_draft_purchase_invoice",
        {
            "supplier": seeded.supplier,
            "items": [{"item_code": seeded.item, "qty": 7, "rate": 5, "expense_account": given}],
        },
    ).data
    saved = draft["items"][0]["expense_account"]
    assert saved != given
    assert draft["warnings"] == [
        f"Row 1 ({seeded.item}): expense account {given} was given, but ERPNext saved {saved}."
    ]
    assert len(comments(site, "Purchase Invoice", draft["name"])) == 1


def test_update_draft_purchase_invoice_to_a_known_bill_no_warns(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_purchase_invoice",
        {
            "supplier": seeded.supplier,
            "bill_no": "E2E-DRAFT-8",
            "items": [{"item_code": seeded.item, "qty": 8, "rate": 5}],
        },
    ).data
    assert draft["warnings"] == []
    updated = mcp.call(
        "update_draft_purchase_invoice",
        {
            "name": draft["name"],
            "modified": draft["modified"],
            "bill_no": "SEED-BILL-1",
            "taxes_and_charges": seeded.purchase_template,
        },
    ).data
    assert (updated["net_total"], updated["grand_total"]) == (40, 47.6)
    [warning] = updated["warnings"]
    assert warning.startswith(f"Possible duplicate of {seeded.purchase_invoice}")
    assert warning.endswith(": a purchase invoice with the same supplier and bill_no.")
    assert stored(site, "Purchase Invoice", draft["name"])["bill_no"] == "SEED-BILL-1"


# Journal entries


def rows(seeded: Seed, amount: str) -> list[dict[str, Any]]:
    """Capital paid into the bank: `amount` per row, a different one per test."""
    return [
        {"account": seeded.bank_ledger, "debit": amount},
        {"account": CAPITAL, "credit": amount},
    ]


def test_create_and_update_draft_journal_entry(mcp: Session, seeded: Seed, site: Site) -> None:
    draft = mcp.call(
        "create_draft_journal_entry",
        {
            "accounts": rows(seeded, "11"),
            "cheque_no": "E2E-11",
            "cheque_date": site_today().isoformat(),
        },
    ).data
    assert (draft["docstatus"], draft["total_debit"], draft["total_credit"]) == (0, 11, 11)
    assert (draft["row_count"], draft["warnings"]) == (2, [])
    updated = mcp.call(
        "update_draft_journal_entry",
        {
            "name": draft["name"],
            "modified": draft["modified"],
            "accounts": rows(seeded, "12"),
            "user_remark": "Corrected",
        },
    ).data
    assert (updated["total_debit"], updated["total_credit"]) == (12, 12)
    doc = stored(site, "Journal Entry", draft["name"])
    assert (doc["voucher_type"], doc["user_remark"], doc["cheque_no"]) == (
        "Journal Entry",
        "Corrected",
        "E2E-11",
    )


def test_rows_erpnext_rounded_out_of_balance_are_a_warning(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    # Balanced as given; each half rounds to the cent, the whole doesn't move
    accounts = [
        {"account": seeded.bank_ledger, "debit": "13.005"},
        {"account": seeded.bank_ledger, "debit": "13.005"},
        {"account": CAPITAL, "credit": "26.01"},
    ]
    draft = mcp.call("create_draft_journal_entry", {"accounts": accounts}).data
    debit, credit = draft["total_debit"], draft["total_credit"]
    assert (debit != credit, credit) == (True, 26.01)
    [warning] = draft["warnings"]
    assert "rounded the rows to the currency's precision" in warning
    [comment] = comments(site, "Journal Entry", draft["name"])
    assert comment["owner"] == AGENT


def test_a_persons_journal_draft_is_a_duplicate(mcp: Session, seeded: Seed, site: Site) -> None:
    theirs = site.insert(
        {
            "doctype": "Journal Entry",
            "company": COMPANY,
            "voucher_type": "Journal Entry",
            "posting_date": site_today().isoformat(),
            "accounts": [
                {"account": CAPITAL, "credit_in_account_currency": 14},
                {"account": seeded.bank_ledger, "debit_in_account_currency": 14},
            ],
        }
    )["name"]
    refused = mcp.call("create_draft_journal_entry", {"accounts": rows(seeded, "14")})
    assert refused.error
    assert refused.text.startswith(
        f"allow_duplicate: a draft with the same posting date and rows exists ({theirs})."
    )


def test_only_journal_entries_of_its_own_voucher_type_are_updated(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    theirs = site.insert(
        {
            "doctype": "Journal Entry",
            "company": COMPANY,
            "voucher_type": "Bank Entry",
            "posting_date": site_today().isoformat(),
            "cheque_no": "E2E-15",
            "cheque_date": site_today().isoformat(),
            "accounts": [
                {"account": seeded.bank_ledger, "debit_in_account_currency": 15},
                {"account": CAPITAL, "credit_in_account_currency": 15},
            ],
        }
    )
    refused = mcp.call(
        "update_draft_journal_entry",
        {"name": theirs["name"], "modified": theirs["modified"], "user_remark": "Changed"},
    )
    assert (refused.error, refused.text) == (
        True,
        f"name: the journal entry {theirs['name']!r} doesn't exist, or the agent user isn't "
        "permitted to read it.",
    )
