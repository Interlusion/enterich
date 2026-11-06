"""ERPNext answers Enterich in English whatever the site's language (REQ-002-PRS-NF006):
with an API key, ERPNext takes the language from the request, not from the agent user."""

from collections.abc import Iterator

import httpx2
import pytest

from tests.e2e.seed import CAPITAL, DEBTORS, Seed, site_today
from tests.e2e.site import Site
from tests.integration.mcp import Session

SETTINGS = ("System Settings", "System Settings")


@pytest.fixture
def german(site: Site, agent: httpx2.Client) -> Iterator[None]:
    """The site's System Settings language German for one test, English again afterwards;
    meanwhile the agent user's key without Enterich gets German answers."""
    before = site.call("frappe.client.get_value", doctype=SETTINGS[0], fieldname="language")
    site.update(*SETTINGS, {"language": "de"})
    try:
        missing = agent.get("/api/resource/Customer/NO-SUCH-CUSTOMER")
        assert "nicht gefunden" in missing.text, missing.text
        yield
    finally:
        site.update(*SETTINGS, {"language": before["language"] or "en"})


def test_reports_come_in_english_on_a_german_site(german: None, mcp: Session, seeded: Seed) -> None:
    y = seeded.posted.year
    report = mcp.call(
        "report_general_ledger",
        {
            "from_date": f"{y}-01-01",
            "to_date": f"{y}-12-31",
            "party_type": "Customer",
            "party": seeded.customer,
        },
    ).data
    assert {r["party_type"] for r in report["records"]} == {"Customer"}


def test_erpnexts_messages_come_in_english_on_a_german_site(
    german: None, mcp: Session, seeded: Seed
) -> None:
    refused = mcp.call(
        "create_draft_journal_entry",
        {
            "accounts": [
                {"account": DEBTORS, "debit": "7"},
                {"account": CAPITAL, "credit": "7"},
            ]
        },
    )
    assert refused.error
    assert "Party Type and Party" in refused.text, refused.text


def test_the_remark_erpnext_writes_is_english_on_a_german_site(
    german: None, mcp: Session, seeded: Seed, site: Site
) -> None:
    draft = mcp.call(
        "create_draft_journal_entry",
        {
            "accounts": [
                {"account": seeded.bank_ledger, "debit": "16"},
                {"account": CAPITAL, "credit": "16"},
            ],
            "cheque_no": "E2E-16",
            "cheque_date": site_today().isoformat(),
        },
    ).data
    doc = site.call("frappe.client.get", doctype="Journal Entry", name=draft["name"])
    assert doc["remark"].startswith("Reference #E2E-16 dated "), doc["remark"]
