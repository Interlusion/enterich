"""The fake ERPNext against the site (analysis 003, section 3.7): nearly every integration
test asserts against `tests/fakes/erpnext.py`, so where the fake answers otherwise than
ERPNext does, those tests pass and prove nothing. The fake's records and the drafts it saves,
the fields its lists take, its refusals as Enterich reports them, and the rows its reports
serve are compared with the site's here, read as the agent user, so an ERPNext upgrade that
the fake doesn't follow fails these tests instead of passing the integration tests."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, cast

import httpx2
import pytest

from enterich.erpnext import Erpnext, Refused
from tests.e2e.seed import COMPANY, Seed, site_today
from tests.e2e.site import HOST, Site
from tests.fakes import erpnext as fake
from tests.fakes.settings import settings

Record = dict[str, Any]
# How many of a DocType's records a field is looked for in: the first that fills it counts
SAMPLE = 25
# The fields every child row has, whatever its DocType
CHILD_FIELDS = {"name", "idx", "parent", "parentfield", "parenttype", "doctype"} | (
    fake.STANDARD_FIELDS
)
NUMBERS = {"Check", "Int", "Float", "Currency", "Percent", "Duration", "Rating"}


def _kind(value: object) -> str:
    """A value's JSON type: a number is one, whole or not; a check field is a number too."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    return type(value).__name__


def _fieldtype_kind(fieldtype: str) -> str:
    if fieldtype in NUMBERS:
        return "number"
    return "list" if fieldtype.startswith("Table") else "str"


def _rows_of(value: object) -> list[Record]:
    if not isinstance(value, list):
        return []
    return [cast("Record", r) for r in cast("list[object]", value) if isinstance(r, dict)]


def differences(
    theirs: Record,
    reals: list[Record],
    at: str = "",
    no_rows: Callable[[str, Record], list[str]] | None = None,
) -> list[str]:
    """Each field of the fake's record that none of ERPNext's has, or that the first of them
    to fill it gives another type; a child table's first row against every real row of it.
    A table without a real row goes to `no_rows`. A field ERPNext has and the fake leaves out
    is no difference: the fake holds what Enterich reads; nor is one no record on the site
    fills, as that depends on the site's data."""
    found: list[str] = []
    for name, value in cast("dict[str, object]", theirs).items():
        holders = [r for r in reals if name in r]
        if not holders:
            found.append(f"{at}{name}: only in the fake")
            continue
        if isinstance(value, list):
            mine = _rows_of(cast("object", value))
            rows = [row for r in holders for row in _rows_of(r[name])]
            if mine and rows:
                found += differences(mine[0], rows, f"{at}{name}[].")
            elif mine:
                found += no_rows(name, mine[0]) if no_rows else [f"{at}{name}: no row on the site"]
            continue
        known: list[object] = [r[name] for r in holders if r[name] is not None]
        if value is None or not known:
            continue
        ours, theirs_kind = _kind(value), _kind(known[0])
        if ours != theirs_kind:
            found.append(f"{at}{name}: the fake's {ours}, ERPNext's {theirs_kind}")
    return found


def _meta(site: Site, doctype: str) -> Record:
    return site.call("frappe.client.get", doctype="DocType", name=doctype)


def _fields(site: Site, doctype: str) -> dict[str, Record]:
    return {f["fieldname"]: f for f in _meta(site, doctype)["fields"] if f.get("fieldname")}


def _against_meta(site: Site, doctype: str) -> Callable[[str, Record], list[str]]:
    """For a child table no record on the site has rows of: the fake's row against the child
    DocType's fields and their types."""

    def check(table: str, row: Record) -> list[str]:
        child = fake.TABLES.get(doctype, {}).get(table)
        if child is None:
            return [f"{table}: no row on the site, and the fake names no child DocType"]
        fields = _fields(site, child)
        found: list[str] = []
        for name, value in cast("dict[str, object]", row).items():
            if name in CHILD_FIELDS:
                continue
            if name not in fields:
                found.append(f"{table}[].{name}: not a field of {child}")
                continue
            kind = _fieldtype_kind(fields[name]["fieldtype"])
            if value is not None and _kind(value) != kind:
                found.append(f"{table}[].{name}: the fake's {_kind(value)}, {child}'s {kind}")
        return found

    return check


def _records(agent: httpx2.Client, doctype: str) -> list[Record]:
    """Up to SAMPLE of the DocType's records in full, as the agent user reads them."""
    params = {"fields": '["name"]', "order_by": "name asc", "limit_page_length": str(SAMPLE)}
    listed = agent.get(f"/api/resource/{doctype}", params=params)
    listed.raise_for_status()
    docs: list[Record] = []
    for row in listed.json()["data"]:
        params = {"doctype": doctype, "name": row["name"]}
        answer = agent.get("/api/method/frappe.client.get", params=params)
        answer.raise_for_status()
        docs.append(answer.json()["message"])
    return docs


# Each DocType the fake answers for, with a record of it as the fake makes one
RECORDS: dict[str, Callable[[], Record]] = {
    "Item": fake.item,
    "Customer": fake.customer,
    "Address": lambda: fake.address("CUST-0001-Billing", "Customer", "CUST-0001"),
    "Sales Invoice": fake.sales_invoice,
    "Sales Taxes and Charges Template": fake.tax_template,
    "Supplier": fake.supplier,
    "Purchase Invoice": fake.purchase_invoice,
    "Purchase Taxes and Charges Template": fake.purchase_tax_template,
    "Account": lambda: fake.account("1200 - Bank Accounts - EX"),
    "Cost Center": lambda: fake.cost_center("Main - EX"),
    "Journal Entry": fake.journal_entry,
    "Fiscal Year": lambda: fake.fiscal_year("2026", "2026-01-01", "2026-12-31", COMPANY),
    "Bank Account": fake.bank_account,
    "Bank Transaction": fake.bank_transaction,
    "Payment Entry": fake.payment_entry,
}


def test_the_fake_has_a_record_for_each_doctype_its_lists_know() -> None:
    children = {t for tables in fake.TABLES.values() for t in tables.values()}
    assert set(fake.FIELDS) - children == set(RECORDS)


@pytest.mark.parametrize("doctype", sorted(RECORDS))
def test_the_fakes_record_has_erpnexts_fields_and_types(
    site: Site, seeded: Seed, agent: httpx2.Client, doctype: str
) -> None:
    real = _records(agent, doctype)
    assert real, f"the seed made no {doctype}"
    assert differences(RECORDS[doctype](), real, no_rows=_against_meta(site, doctype)) == []


def _saved(doctype: str, body: Record) -> Record:
    """The document the fake saves for the body Enterich would send to create a draft."""
    erp = fake.FakeErpnext()
    erp.add("Customer", fake.customer("CUST-0001"))
    erp.add("Supplier", fake.supplier("SUPP-0001"))
    erp.add("Sales Taxes and Charges Template", fake.tax_template("VAT 19% - EX"))
    erp.add("Account", fake.account("1200 - Bank Accounts - EX"))
    erp.add("Account", fake.account("5000 - Cost - EX"))
    erp.add("Bank Account", fake.bank_account())
    client = Erpnext(settings(), erp.transport())

    async def insert() -> Record:
        try:
            return await client.insert(doctype, body)
        finally:
            await client.aclose()

    return asyncio.run(insert())


DRAFTED: dict[str, Record] = {
    "Sales Invoice": {
        "customer": "CUST-0001",
        "posting_date": "2026-10-29",
        "set_posting_time": 1,
        "items": [{"item_code": "SKU-1", "qty": 1, "rate": 10}],
        "taxes_and_charges": "VAT 19% - EX",
        "taxes": fake.tax_template("VAT 19% - EX")["taxes"],
    },
    "Purchase Invoice": {
        "supplier": "SUPP-0001",
        "posting_date": "2026-10-29",
        "set_posting_time": 1,
        "bill_no": "B-1",
        "items": [{"item_code": "SKU-1", "qty": 1, "rate": 10}],
    },
    "Journal Entry": {
        "voucher_type": "Journal Entry",
        "posting_date": "2026-10-29",
        "multi_currency": 0,
        "accounts": [
            {"account": "5000 - Cost - EX", "debit_in_account_currency": 10},
            {"account": "1200 - Bank Accounts - EX", "credit_in_account_currency": 10},
        ],
    },
    "Payment Entry": {
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": "CUST-0001",
        "posting_date": "2026-10-29",
        "paid_to": "1200 - Bank Accounts - EX",
        "bank_account": "Main - Example Bank",
        "paid_amount": 10,
        "received_amount": 10,
        "reference_no": "R-1",
        "reference_date": "2026-10-29",
    },
}


@pytest.mark.parametrize("doctype", sorted(DRAFTED))
def test_the_draft_the_fake_saves_has_erpnexts_fields_and_types(
    site: Site, seeded: Seed, agent: httpx2.Client, doctype: str
) -> None:
    """What Enterich reads back after a create or an update."""
    saved = _saved(doctype, {**DRAFTED[doctype], "company": fake.COMPANY, "docstatus": 0})
    real = _records(agent, doctype)
    assert differences(saved, real, no_rows=_against_meta(site, doctype)) == []


@pytest.mark.parametrize("doctype", sorted(fake.FIELDS))
def test_the_fields_the_fakes_lists_take_are_erpnexts(
    site: Site, seeded: Seed, doctype: str
) -> None:
    """The fake refuses a list field it doesn't know, as ERPNext does: each it knows is one of
    the DocType's, each child table it knows holds the DocType it names, and a list the agent
    user may only select from returns the DocType's search fields among them."""
    meta = _meta(site, doctype)
    fields = _fields(site, doctype)
    assert sorted(fake.FIELDS[doctype] - set(fields)) == []
    tables = {n: f["options"] for n, f in fields.items() if f["fieldtype"].startswith("Table")}
    known = fake.TABLES.get(doctype, {})
    assert {t: tables.get(t) for t in known} == known
    if doctype in fake.SEARCH_FIELDS:
        search = {s.strip() for s in (meta.get("search_fields") or "").split(",") if s.strip()}
        assert search & fake.FIELDS[doctype] == fake.SEARCH_FIELDS[doctype]


Request = Callable[[Erpnext], Awaitable[object]]

# Requests ERPNext refuses, each as Enterich sends it
REFUSED: dict[str, Request] = {
    "a list of a field the DocType lacks": lambda c: c.get_list(
        "Sales Invoice",
        fields=["name", "no_such_field"],
        order_by="name asc",
        start=0,
        page_length=1,
    ),
    "a list filtered on a field the DocType lacks": lambda c: c.get_list(
        "Sales Invoice",
        fields=["name"],
        filters=[["no_such_field", "=", 1]],
        order_by="name asc",
        start=0,
        page_length=1,
    ),
    "a document that doesn't exist": lambda c: c.get_doc("Sales Invoice", "NOPE-1"),
    "an update of a document that doesn't exist": lambda c: c.update(
        "Sales Invoice", "NOPE-1", {"remarks": "x"}
    ),
    "the rows of a tax template that doesn't exist": lambda c: c.tax_rows(
        "Sales Taxes and Charges Template", "NOPE"
    ),
}


def _refusal(client: Erpnext, request: Request) -> tuple[int, str | None, str]:
    async def call() -> tuple[int, str | None, str]:
        try:
            await request(client)
        except Refused as refused:
            return refused.status, refused.exc_type, str(refused)
        finally:
            await client.aclose()
        raise AssertionError("not refused")

    return asyncio.run(call())


@pytest.mark.parametrize("request_", list(REFUSED.values()), ids=list(REFUSED))
def test_the_fake_refuses_as_erpnext_does(url: str, seeded: Seed, request_: Request) -> None:
    """The status, the exception's type and the text Enterich makes of them, ERPNext's message
    included (REQ-001-PRS-F008)."""
    on_site = settings(
        erpnext_url=url,
        erpnext_host=HOST,
        erpnext_api_key=seeded.api_key,
        erpnext_api_secret=seeded.api_secret,
        company=COMPANY,
    )
    real = _refusal(Erpnext(on_site), request_)
    faked = _refusal(Erpnext(settings(), fake.FakeErpnext().transport()), request_)
    assert faked == real


def test_a_refusal_a_test_gives_the_fake_has_erpnexts_fields(
    agent: httpx2.Client, seeded: Seed
) -> None:
    """A test makes the fake refuse with fake.error(): its body has the fields of ERPNext's
    for a list without the read right, the refusal the tests give it most."""
    real = agent.get("/api/resource/Bank Guarantee", params={"fields": '["name"]'})
    assert real.status_code == 403
    assert sorted(fake.error(403, "PermissionError", "x")) == sorted(real.json())


def _report(site: Site, report: str, filters: Record) -> list[Any]:
    answer = site.call(
        "frappe.desk.query_report.run",
        report_name=report,
        filters=filters,
        are_default_filters=False,
    )
    return answer["result"]


def _dicts(rows: list[Any]) -> list[Record]:
    return [cast("Record", r) for r in rows if isinstance(r, dict)]


def test_the_fakes_report_rows_are_erpnexts(site: Site, seeded: Seed) -> None:
    """Each report Enterich runs, with the filters it sends: the rows the fake serves against
    the site's, the summary and total rows that Enterich finds by their place among them."""
    today = site_today().isoformat()
    year_start = f"{today[:4]}-01-01"
    found: dict[str, list[str]] = {}
    aged = {
        "company": COMPANY,
        "report_date": today,
        "ageing_based_on": "Due Date",
        "age_as_on": "Report Date",
        "range": "30, 60, 90, 120",
    }
    for report, row, party in (
        ("Accounts Receivable", fake.receivable("X", 1.0), "Customer"),
        ("Accounts Payable", fake.payable("X", 1.0), "Supplier"),
    ):
        real = _report(site, report, {**aged, "party_type": party})
        found[report] = differences(row, _dicts(real))
        # Frappe appends the total row as a list, which Enterich leaves out
        if report not in fake.TOTAL_ROW_REPORTS or not (real and isinstance(real[-1], list)):
            found[report].append("no total row as a list")
    ledger = _dicts(
        _report(
            site,
            "General Ledger",
            {
                "company": COMPANY,
                "from_date": year_start,
                "to_date": today,
                "include_default_book_entries": 1,
                "show_remarks": 1,
            },
        )
    )
    served = fake.ledger([fake.ledger_entry("X", 1.0, 0.0)])
    summaries = (ledger[0], ledger[-2], ledger[-1])
    found["General Ledger"] = [
        *differences(served[0], ledger[:1], "opening."),
        *differences(served[1], ledger[1:-2], "entry."),
        *differences(served[-2], ledger[-2:-1], "total."),
        *differences(served[-1], ledger[-1:], "closing."),
        # Enterich tells the summary rows from the entries by their posting date
        *(
            ["a summary row with a posting date"]
            if any(r.get("posting_date") for r in summaries)
            else []
        ),
    ]
    balance = [
        r
        for r in _dicts(
            _report(
                site,
                "Trial Balance",
                {
                    "company": COMPANY,
                    "fiscal_year": today[:4],
                    "from_date": year_start,
                    "to_date": today,
                    "show_zero_values": 0,
                    "with_period_closing_entry_for_opening": 1,
                    "with_period_closing_entry_for_current_period": 1,
                    "include_default_book_entries": 1,
                    "show_net_values": 1,
                    "show_group_accounts": 1,
                },
            )
        )
        if r
    ]
    account = fake.balance_row("1200 - Bank Accounts - EX", None, False)
    found["Trial Balance"] = [
        *differences(account, balance[:-1]),
        *differences(fake.balance_total([account]), balance[-1:], "total."),
        # Enterich finds the total row as the only one without is_group_account
        *(["a total row with is_group_account"] if "is_group_account" in balance[-1] else []),
    ]
    assert found == {report: [] for report in found}
