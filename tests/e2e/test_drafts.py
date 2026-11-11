"""The drafts against the seeded site: create and update as the agent user, the warnings
as a comment on the draft, and the duplicate check with drafts and invoices people made
(REQ-001 Drafts, REQ-004-PRS-F005 to REQ-004-PRS-F008, REQ-005-PRS-F005 to
REQ-005-PRS-F009, REQ-006-PRS-F005 to REQ-006-PRS-F008, REQ-007-PRS-F004 to
REQ-007-PRS-F007), the limit of drafts per hour (REQ-001-PRS-F019), and the tax rows
ERPNext adds from item tax templates (REQ-001-PRS-F020), and the tax summary
(REQ-001-PRS-F022).

The seed removes earlier runs' drafts; within a run, each test uses its own quantities
or amounts, so no test's draft is another's duplicate by party, date and items or rows,
and its own bank reference for a payment.
By bill_no they are: two tests make drafts with the seeded purchase invoice's, which the
duplicate check finds too, so those tests expect the seeded invoice first, not alone."""

from typing import Any

from tests.conftest import Logs
from tests.e2e.seed import (
    AGENT,
    CAPITAL,
    COMPANY,
    DEBTORS,
    EU_PURCHASE,
    INPUT_VAT,
    SALES_VAT,
    SALES_VAT_7,
    Seed,
    advances_apart,
    site_today,
)
from tests.e2e.site import Site
from tests.integration.mcp import Session

# The setup wizard's default sales template: its rates are 0 % and come from item tax
# templates, which only the seeded item_taxed_19 has.
ZERO_TEMPLATE = "Lieferung oder sonstige Leistung im Inland - EX"


def comments(site: Site, doctype: str, name: str) -> list[dict[str, Any]]:
    return site.get_list(
        "Comment",
        {"reference_doctype": doctype, "reference_name": name, "comment_type": "Comment"},
        ["content", "owner"],
    )


def stored(site: Site, doctype: str, name: str) -> dict[str, Any]:
    return site.call("frappe.client.get", doctype=doctype, name=name)


def summary(result: dict[str, Any]) -> list[tuple[str, float, float, float]]:
    return [
        (e["account_head"], e["rate"], e["taxable_amount"], e["tax_amount"])
        for e in result["tax_summary"]
    ]


# Sales invoices


def test_create_draft_sales_invoice(mcp: Session, seeded: Seed, site: Site, logs: Logs) -> None:
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
    [line] = logs.events("operation")
    [comment] = comments(site, "Sales Invoice", draft["name"])
    assert comment["owner"] == AGENT
    assert comment["content"] == f"Enterich: create_draft_sales_invoice, call {line['call']}."


def test_the_limit_counts_the_hour_in_the_sites_time(
    mcp: Session, limited: Session, seeded: Seed, site: Site
) -> None:
    """ERPNext's `creation` is in the site's time zone, without a zone; a draft just made
    counts towards the hour Enterich counts back in ENTERICH_TIMEZONE."""
    made = mcp.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": [{"item_code": seeded.item, "qty": 13, "rate": 1}]},
    )
    assert not made.error, made.text
    mine = {"owner": AGENT, "docstatus": 0}
    before = site.get_list("Sales Invoice", mine, ["name"])
    result = limited.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": [{"item_code": seeded.item, "qty": 14, "rate": 1}]},
    )
    assert result.error
    assert "(ENTERICH_MAX_DRAFTS_PER_HOUR)" in result.text
    assert site.get_list("Sales Invoice", mine, ["name"]) == before


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
    assert comment["content"].startswith("Enterich: create_draft_sales_invoice, call ")
    assert comment["content"].endswith("<br>" + "<br>".join(draft["warnings"]))


def test_a_tax_row_keeps_its_rate_when_an_item_tax_template_taxes_the_item(
    mcp: Session, seeded: Seed
) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {
            "customer": seeded.customer,
            "items": [{"item_code": seeded.item_taxed_19, "qty": 1, "rate": 100}],
            "taxes_and_charges": ZERO_TEMPLATE,
        },
    ).data
    assert (draft["net_total"], draft["grand_total"], draft["warnings"]) == (100, 119, [])
    [row] = [r for r in draft["taxes"] if r["account_head"] == SALES_VAT[1]]
    assert (row["rate"], row["tax_amount"]) == (0, 19)


def test_without_a_tax_template_erpnext_adds_rows_from_the_item_tax_template(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {
            "customer": seeded.customer,
            "items": [{"item_code": seeded.item_taxed_19, "qty": 2, "rate": 100}],
        },
    ).data
    rows = draft["taxes"]
    # Every VAT account of the chart, input VAT among them; 7 of them at 19 %
    assert (len(rows), {r["rate"] for r in rows}) == (13, {0})
    assert INPUT_VAT[1] in {r["account_head"] for r in rows}
    assert [r["tax_amount"] for r in rows if r["account_head"] == SALES_VAT[1]] == [38]
    assert draft["total_taxes_and_charges"] == 266
    # The 7 rows that tax the item, none at 0 % on 0 for the others
    taxed = [r["account_head"] for r in rows if r["tax_amount"]]
    assert summary(draft) == [(account, 19, 200, 38) for account in taxed]
    warning = (
        "The draft has 13 tax rows, with 266.00 of tax, that ERPNext added from the items' "
        "item tax templates when it was saved without tax rows; check them in `taxes`, or "
        "give `taxes_and_charges` to replace them."
    )
    assert draft["warnings"] == [warning]
    # No default template either, unlike the desk's form
    assert not stored(site, "Sales Invoice", draft["name"])["taxes_and_charges"]
    # The rows keep their mark through an update of the remarks
    again = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": draft["modified"], "remarks": "Checked"},
    ).data
    assert again["warnings"] == [warning]
    replaced = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": again["modified"], "taxes_and_charges": ZERO_TEMPLATE},
    ).data
    assert (len(replaced["taxes"]), replaced["total_taxes_and_charges"]) == (2, 38)
    assert replaced["warnings"] == []


def test_a_purchase_draft_without_a_tax_template_gets_no_default(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_purchase_invoice",
        {
            "supplier": seeded.supplier,
            "bill_no": "E2E-NOTAX-1",
            "items": [{"item_code": seeded.item, "qty": 1, "rate": 13}],
        },
    ).data
    assert not stored(site, "Purchase Invoice", draft["name"])["taxes_and_charges"]


def test_a_reverse_charge_purchase_draft_adds_and_deducts_and_doesnt_warn(
    mcp: Session, seeded: Seed
) -> None:
    draft = mcp.call(
        "create_draft_purchase_invoice",
        {
            "supplier": seeded.supplier,
            "bill_no": "E2E-EU-1",
            "items": [{"item_code": seeded.item_taxed_19, "qty": 1, "rate": 100}],
            "taxes_and_charges": EU_PURCHASE,
        },
    ).data
    taxed = [(t["add_deduct_tax"], t["tax_amount"]) for t in draft["taxes"] if t["tax_amount"]]
    assert sorted(taxed) == [("Add", 19), ("Deduct", 19)]
    assert (draft["total_taxes_and_charges"], draft["warnings"]) == (0, [])
    # Both rows, each positive as its tax_amount; none for the 7 % rows the item's
    # template marks not applicable
    accounts = [t["account_head"] for t in draft["taxes"] if t["tax_amount"]]
    assert summary(draft) == [(account, 19, 100, 19) for account in accounts]


def test_the_tax_summary_gives_each_rate_with_what_it_taxed(mcp: Session, seeded: Seed) -> None:
    items = [
        {"item_code": seeded.item_taxed_19, "qty": 2, "rate": 100},
        {"item_code": seeded.item_taxed_7, "qty": 1, "rate": 100},
    ]
    draft = mcp.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": items, "taxes_and_charges": ZERO_TEMPLATE},
    ).data
    assert {t["rate"] for t in draft["taxes"]} == {0}
    assert summary(draft) == [(SALES_VAT[1], 19, 200, 38), (SALES_VAT_7, 7, 100, 7)]
    got = mcp.call("get_sales_invoice", {"name": draft["name"]}).data
    assert got["tax_summary"] == draft["tax_summary"]
    # An item without an item tax template is taxed at the rows' 0 %
    untaxed = {"item_code": seeded.item, "qty": 1, "rate": 50}
    updated = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": draft["modified"], "items": [*items, untaxed]},
    ).data
    assert summary(updated) == [
        (SALES_VAT[1], 19, 200, 38),
        (SALES_VAT[1], 0, 50, 0),
        (SALES_VAT_7, 7, 100, 7),
        (SALES_VAT_7, 0, 50, 0),
    ]


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


def test_a_persons_draft_isnt_updated(mcp: Session, seeded: Seed, site: Site) -> None:
    theirs = site.insert(
        {
            "doctype": "Sales Invoice",
            "company": COMPANY,
            "customer": seeded.customer,
            "items": [{"item_code": seeded.item, "qty": 9, "rate": 10}],
        }
    )
    refused = mcp.call(
        "update_draft_sales_invoice",
        {"name": theirs["name"], "modified": theirs["modified"], "remarks": "Changed"},
    )
    assert (refused.error, refused.text) == (
        True,
        f"name: {theirs['name']} was created by another user; only drafts the agent user "
        "created can be updated.",
    )
    assert stored(site, "Sales Invoice", theirs["name"])["modified"] == theirs["modified"]


def test_the_agents_draft_a_person_edited_is_updated(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_sales_invoice",
        {"customer": seeded.customer, "items": [{"item_code": seeded.item, "qty": 11}]},
    ).data
    edited = site.update("Sales Invoice", draft["name"], {"remarks": "Checked"})
    updated = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": edited["modified"], "remarks": "Agent's again"},
    )
    assert not updated.error, updated.text
    doc = stored(site, "Sales Invoice", draft["name"])
    assert (doc["owner"], doc["remarks"]) == (AGENT, "Agent's again")


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


# Returns


def test_create_and_update_draft_sales_return(mcp: Session, seeded: Seed, site: Site) -> None:
    one = [{"item_code": seeded.item, "qty": 1}]
    arguments = {"return_against": seeded.sales_invoice, "items": one, "allow_duplicate": True}
    draft = mcp.call("create_draft_sales_return", arguments).data
    assert (draft["return_against"], draft["docstatus"]) == (seeded.sales_invoice, 0)
    assert (draft["net_total"], draft["grand_total"]) == (-50, -59.5)
    assert summary(draft) == [(SALES_VAT[1], 19, -50, -9.5)]
    assert [(r["item_code"], r["qty"]) for r in draft["items"]] == [(seeded.item, -1)]
    doc = stored(site, "Sales Invoice", draft["name"])
    invoice = stored(site, "Sales Invoice", seeded.sales_invoice)
    assert (doc["is_return"], doc["owner"]) == (1, AGENT)
    assert doc["items"][0]["sales_invoice_item"] == invoice["items"][0]["name"]
    again = mcp.call("create_draft_sales_return", {**arguments, "allow_duplicate": False})
    assert again.error
    assert again.text.startswith("allow_duplicate: ")
    assert draft["name"] in again.text
    updated = mcp.call(
        "update_draft_sales_return",
        {
            "name": draft["name"],
            "modified": draft["modified"],
            "items": [{"item_code": seeded.item, "qty": 2}],
        },
    ).data
    assert updated["grand_total"] == -119
    refused = mcp.call(
        "update_draft_sales_invoice",
        {"name": draft["name"], "modified": updated["modified"], "remarks": "Changed"},
    )
    assert refused.error
    assert "update_draft_sales_return" in refused.text


def test_a_return_above_what_is_left_is_refused(mcp: Session, seeded: Seed) -> None:
    refused = mcp.call(
        "create_draft_sales_return",
        {"return_against": seeded.sales_invoice, "items": [{"item_code": seeded.item, "qty": 3}]},
    )
    assert refused.error
    assert refused.text.startswith("items: ")
    assert "2 left" in refused.text


def test_a_return_on_the_invoices_day_takes_its_posting_time(
    mcp: Session, seeded: Seed, site: Site
) -> None:
    invoice = stored(site, "Sales Invoice", seeded.sales_invoice)
    arguments = {
        "return_against": seeded.sales_invoice,
        "items": [{"item_code": seeded.item, "qty": 1}],
        "posting_date": invoice["posting_date"],
        "allow_duplicate": True,
    }
    draft = mcp.call("create_draft_sales_return", arguments)
    assert not draft.error, draft.text
    doc = stored(site, "Sales Invoice", draft.data["name"])
    assert (doc["posting_date"], doc["posting_time"]) == (
        invoice["posting_date"],
        invoice["posting_time"],
    )


def test_a_debit_note_with_the_credit_notes_number(mcp: Session, seeded: Seed, site: Site) -> None:
    draft = mcp.call(
        "create_draft_purchase_return",
        {
            "return_against": seeded.purchase_invoice,
            "bill_no": "E2E-CN-1",
            "allow_duplicate": True,
        },
    ).data
    assert (draft["outside_text"]["bill_no"], draft["supplier"]) == ("E2E-CN-1", seeded.supplier)
    assert (draft["grand_total"], draft["posting_date"]) == (-47.6, site_today().isoformat())
    doc = stored(site, "Purchase Invoice", draft["name"])
    assert (doc["is_return"], doc["return_against"]) == (1, seeded.purchase_invoice)


# Payment entries


def test_create_and_update_draft_payment_entry(mcp: Session, seeded: Seed, site: Site) -> None:
    # The seeded payment left 69 of the seeded invoice open
    draft = mcp.call(
        "create_draft_payment_entry",
        {
            "party_type": "Customer",
            "party": seeded.customer,
            "bank_account": seeded.bank_account,
            "paid_amount": "30",
            "reference_no": "E2E-PAY-1",
            "references": [{"reference_name": seeded.sales_invoice, "allocated_amount": "20"}],
        },
    ).data
    assert (draft["payment_type"], draft["status"], draft["docstatus"]) == ("Receive", "Draft", 0)
    assert (draft["paid_from"], draft["paid_to"]) == (DEBTORS, seeded.bank_ledger)
    assert (draft["paid_amount"], draft["received_amount"]) == (30, 30)
    assert (draft["total_allocated_amount"], draft["unallocated_amount"]) == (20, 10)
    assert draft["references"] == [
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": seeded.sales_invoice,
            "allocated_amount": 20,
            "outstanding_amount": 69,
            "outside_text": {},
        }
    ]
    assert draft["reference_date"] == draft["posting_date"] == site_today().isoformat()
    [warning] = draft["warnings"]
    assert "10" in warning
    [comment] = comments(site, "Payment Entry", draft["name"])
    assert comment["owner"] == AGENT
    updated = mcp.call(
        "update_draft_payment_entry",
        {"name": draft["name"], "modified": draft["modified"], "paid_amount": "20"},
    ).data
    assert (updated["unallocated_amount"], updated["warnings"]) == (0, [])
    doc = stored(site, "Payment Entry", draft["name"])
    assert (doc["owner"], doc["bank_account"], doc["reference_no"]) == (
        AGENT,
        seeded.bank_account,
        "E2E-PAY-1",
    )


def test_an_advance_takes_invoices_later(mcp: Session, seeded: Seed, site: Site) -> None:
    advances = advances_apart(site, on=True)
    try:
        draft = mcp.call(
            "create_draft_payment_entry",
            {
                "party_type": "Customer",
                "party": seeded.customer,
                "bank_account": seeded.bank_account,
                "paid_amount": "12",
                "reference_no": "E2E-PAY-4",
            },
        ).data
        assert draft["paid_from"] == advances
        updated = mcp.call(
            "update_draft_payment_entry",
            {
                "name": draft["name"],
                "modified": draft["modified"],
                "references": [{"reference_name": seeded.sales_invoice, "allocated_amount": "12"}],
            },
        )
        assert not updated.error, updated.text
        assert (updated.data["paid_from"], updated.data["unallocated_amount"]) == (DEBTORS, 0)
    finally:
        advances_apart(site, on=False)


def test_a_payment_to_a_supplier(mcp: Session, seeded: Seed) -> None:
    draft = mcp.call(
        "create_draft_payment_entry",
        {
            "party_type": "Supplier",
            "party": seeded.supplier,
            "bank_account": seeded.bank_account,
            "paid_amount": "47.6",
            "reference_no": "E2E-PAY-2",
            "references": [{"reference_name": seeded.purchase_invoice, "allocated_amount": "47.6"}],
        },
    ).data
    assert (draft["payment_type"], draft["paid_from"]) == ("Pay", seeded.bank_ledger)
    assert (draft["unallocated_amount"], draft["warnings"]) == (0, [])


def test_a_recorded_bank_reference_is_a_duplicate(mcp: Session, seeded: Seed) -> None:
    refused = mcp.call(
        "create_draft_payment_entry",
        {
            "party_type": "Customer",
            "party": seeded.customer,
            "bank_account": seeded.bank_account,
            "paid_amount": "50",
            "reference_no": "SEED-PAY-1",
        },
    )
    assert refused.error
    assert refused.text.startswith("allow_duplicate: ")
    assert seeded.payment_entry in refused.text


def test_an_allocation_above_what_is_open_is_refused(mcp: Session, seeded: Seed) -> None:
    refused = mcp.call(
        "create_draft_payment_entry",
        {
            "party_type": "Customer",
            "party": seeded.customer,
            "bank_account": seeded.bank_account,
            "paid_amount": "70",
            "reference_no": "E2E-PAY-3",
            "references": [{"reference_name": seeded.sales_invoice, "allocated_amount": "70"}],
        },
    )
    assert refused.error
    assert refused.text.startswith("references: ")
    assert "69" in refused.text
