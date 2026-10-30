"""The ceiling: what ERPNext's role allows the agent user's key, called directly as anyone
holding the key could, not through Enterich (REQ-001-URS-F003, ADR-001).

The role refuses submit, cancel and delete, and any change to a submitted document. Two
doors stay open, as REQ-001-URS-F003 says: a draft is discarded with write alone, and a
cancelled document is amended with create alone. Only Enterich's fixed operations close
them (REQ-001-PRS-F006).

The drafts here use quantities and amounts from 31 up, which test_drafts.py doesn't use,
so none is a duplicate there."""

import json
from collections.abc import Callable
from typing import Any

import httpx2
import pytest

from tests.e2e.seed import CAPITAL, COMPANY, DRAFTED, Seed, remove, site_today
from tests.e2e.site import Site

# Inserts a draft of the DocType with the amount as the agent user
Draft = Callable[[str, int], dict[str, Any]]


def draft_body(seeded: Seed, doctype: str, amount: int) -> dict[str, Any]:
    """A draft the agent user may insert: it holds create and write."""
    items = [{"item_code": seeded.item, "qty": amount, "rate": 1}]
    if doctype == "Sales Invoice":
        return {"customer": seeded.customer, "items": items}
    if doctype == "Purchase Invoice":
        return {"supplier": seeded.supplier, "items": items}
    return {
        "voucher_type": "Journal Entry",
        "posting_date": site_today().isoformat(),
        "accounts": [
            {"account": seeded.bank_ledger, "debit_in_account_currency": amount},
            {"account": CAPITAL, "credit_in_account_currency": amount},
        ],
    }


def resource(doctype: str, name: str = "") -> str:
    return f"/api/resource/{doctype}" + (f"/{name}" if name else "")


def insert(agent: httpx2.Client, doctype: str, doc: dict[str, Any]) -> httpx2.Response:
    return agent.post(resource(doctype), json={"company": COMPANY, **doc})


def refused(response: httpx2.Response) -> bool:
    """ERPNext's permission refusal."""
    return response.status_code == 403 and response.json().get("exc_type") == "PermissionError"


def docstatus(site: Site, doctype: str, name: str) -> int:
    return site.get_list(doctype, {"name": name}, ["docstatus"])[0]["docstatus"]


@pytest.fixture
def draft(agent: httpx2.Client, seeded: Seed) -> Draft:
    def make(doctype: str, amount: int) -> dict[str, Any]:
        response = insert(agent, doctype, draft_body(seeded, doctype, amount))
        assert response.status_code == 200, response.text
        return response.json()["data"]

    return make


@pytest.mark.parametrize("doctype", DRAFTED)
def test_the_agents_key_cannot_submit(
    agent: httpx2.Client,
    seeded: Seed,
    site: Site,
    draft: Draft,
    doctype: str,
) -> None:
    submitted = {**draft_body(seeded, doctype, 31), "docstatus": 1}
    assert refused(insert(agent, doctype, submitted))
    doc = draft(doctype, 32)
    assert refused(agent.put(resource(doctype, doc["name"]), json={"docstatus": 1}))
    assert refused(agent.post("/api/method/frappe.client.submit", data={"doc": json.dumps(doc)}))
    assert docstatus(site, doctype, doc["name"]) == 0


@pytest.mark.parametrize("doctype", DRAFTED)
def test_the_agents_key_cannot_delete(
    agent: httpx2.Client, site: Site, draft: Draft, doctype: str
) -> None:
    doc = draft(doctype, 33)
    assert refused(agent.delete(resource(doctype, doc["name"])))
    assert refused(
        agent.post(
            "/api/method/frappe.client.delete", data={"doctype": doctype, "name": doc["name"]}
        )
    )
    assert docstatus(site, doctype, doc["name"]) == 0


def submitted(seeded: Seed, doctype: str) -> str:
    return {
        "Sales Invoice": seeded.sales_invoice,
        "Purchase Invoice": seeded.purchase_invoice,
        "Journal Entry": seeded.journal_entry,
    }[doctype]


@pytest.mark.parametrize("doctype", DRAFTED)
def test_the_agents_key_cannot_cancel_or_change_a_submitted_document(
    agent: httpx2.Client, seeded: Seed, site: Site, doctype: str
) -> None:
    name = submitted(seeded, doctype)
    before = site.get_list(doctype, {"name": name}, ["docstatus", "modified"])
    by_name = {"doctype": doctype, "name": name}
    assert refused(agent.post("/api/method/frappe.client.cancel", data=by_name))
    assert refused(agent.post("/api/method/frappe.desk.form.save.cancel", data=by_name))
    assert refused(agent.put(resource(doctype, name), json={"docstatus": 2}))
    assert refused(agent.put(resource(doctype, name), json={"title": "Changed"}))
    assert site.get_list(doctype, {"name": name}, ["docstatus", "modified"]) == before


@pytest.mark.parametrize("doctype", DRAFTED)
def test_a_draft_is_discarded_with_write_alone(
    agent: httpx2.Client, site: Site, draft: Draft, doctype: str
) -> None:
    doc = draft(doctype, 34)
    try:
        response = agent.post(
            "/api/method/frappe.desk.form.save.discard",
            data={"doctype": doctype, "name": doc["name"]},
        )
        assert response.status_code == 200, response.text
        assert docstatus(site, doctype, doc["name"]) == 2
    finally:
        # The seed removes only drafts, and this one was the last of its series: its name
        # comes again
        remove(site, [(doctype, doc["name"])])


@pytest.mark.parametrize("doctype", DRAFTED)
def test_a_cancelled_document_is_amended_with_create_alone(
    agent: httpx2.Client, seeded: Seed, doctype: str
) -> None:
    cancelled = seeded.cancelled[doctype]
    body = {**draft_body(seeded, doctype, 35), "amended_from": cancelled}
    response = insert(agent, doctype, body)
    assert response.status_code == 200, response.text
    amendment = response.json()["data"]
    assert (amendment["name"], amendment["docstatus"]) == (f"{cancelled}-1", 0)
