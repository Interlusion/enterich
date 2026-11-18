"""The fake ERPNext against the site (analysis 003, section 3.7): nearly every integration
test asserts against `tests/fakes/erpnext.py`, so where the fake answers otherwise than
ERPNext does, those tests pass and prove nothing. The fake's records and the drafts it saves,
the fields its lists take, its refusals as Enterich reports them, and the rows its reports
serve are compared with the site's here, read as the agent user, and so is what it imitates
of ERPNext's behaviour: pricing rules, the supplier's bill number checked for uniqueness,
prepared and snapshot reports. An ERPNext upgrade that the fake doesn't follow fails these
tests instead of passing the integration tests. A report's mode is set with `bench`, which
needs the compose site's backend container."""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable, Generator, Iterator
from contextlib import contextmanager
from typing import Any, cast

import httpx2
import pytest

from enterich.erpnext import Erpnext, Refused
from tests.e2e.seed import COMPANY, STOCK_NOT_BILLED, Seed, remove, site_today
from tests.e2e.site import HOST, Site, bench
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


def _on_site(url: str, seeded: Seed) -> Erpnext:
    """Enterich's client for the site, as the agent user."""
    return Erpnext(
        settings(
            erpnext_url=url,
            erpnext_host=HOST,
            erpnext_api_key=seeded.api_key,
            erpnext_api_secret=seeded.api_secret,
            company=COMPANY,
        )
    )


def _on_fake(erp: fake.FakeErpnext) -> Erpnext:
    return Erpnext(settings(), erp.transport())


@pytest.mark.parametrize("request_", list(REFUSED.values()), ids=list(REFUSED))
def test_the_fake_refuses_as_erpnext_does(url: str, seeded: Seed, request_: Request) -> None:
    """The status, the exception's type and the text Enterich makes of them, ERPNext's message
    included (REQ-001-PRS-F008)."""
    real = _refusal(_on_site(url, seeded), request_)
    faked = _refusal(_on_fake(fake.FakeErpnext()), request_)
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


# What the fake imitates of ERPNext's behaviour, each set up on the site and on the fake
# alike, with the same request sent to both through Enterich's client


def _sent(client: Erpnext, request: Callable[[Erpnext], Awaitable[Record]]) -> Record:
    async def call() -> Record:
        try:
            return await request(client)
        finally:
            await client.aclose()

    return asyncio.run(call())


# Each kind of pricing rule, for the seeded item at a rate that isn't its price
RULES: dict[str, Record] = {
    "price": {"price_or_product_discount": "Price", "rate_or_discount": "Rate", "rate": 45},
    "product": {"price_or_product_discount": "Product", "same_item": 0, "free_qty": 1},
}
# A product rule on the item without a price, which keeps the rate given
UNPRICED = "product, no price"


def _priced(doc: Record) -> list[tuple[Any, ...]]:
    """What Enterich reads of a saved draft's rows to warn of a replaced rate."""
    return [
        (r["item_code"], r["qty"], r["rate"], r["is_free_item"], bool(r.get("pricing_rules")))
        for r in _rows_of(doc["items"])
    ]


@pytest.mark.parametrize("kind", [*sorted(RULES), UNPRICED])
def test_a_pricing_rule_sets_the_rows_the_fake_sets(
    url: str, site: Site, seeded: Seed, kind: str
) -> None:
    """A price rule sets its rate; a product rule adds the free-item row and sets the paid
    row to the price list's rate, where the item has one. Both name the rule on the row."""
    item, free = seeded.item, seeded.unpriced_item
    if kind == UNPRICED:
        item, free = free, item
    prices = site.get_list(
        "Item Price", {"item_code": item, "price_list": "Standard Selling"}, ["price_list_rate"]
    )
    rule_of = RULES["product" if kind == UNPRICED else kind]
    product = {"free_item": free} if kind != "price" else {}
    rule = site.insert(
        {
            "doctype": "Pricing Rule",
            "title": f"E2E {kind} rule",
            "apply_on": "Item Code",
            "items": [{"item_code": item}],
            "selling": 1,
            "company": COMPANY,
            **rule_of,
            **product,
        }
    )["name"]
    body = {"customer": seeded.customer, "items": [{"item_code": item, "qty": 2, "rate": 48}]}
    try:
        real = _sent(_on_site(url, seeded), lambda c: c.insert("Sales Invoice", body))
        # The draft's table of applied rules links to the rule, so the draft goes first
        remove(site, [("Sales Invoice", real["name"])])
    finally:
        site.delete("Pricing Rule", rule)
    erp = fake.FakeErpnext()
    erp.add("Customer", fake.customer(seeded.customer))
    if prices:
        erp.prices[item] = prices[0]["price_list_rate"]
    if kind == "price":
        erp.rules[item] = rule_of["rate"]
    else:
        erp.free_items[item] = free
    faked = _sent(_on_fake(erp), lambda c: c.insert("Sales Invoice", body))
    assert _priced(faked) == _priced(real)


UNIQUENESS = ("Accounts Settings", "check_supplier_invoice_uniqueness")
# The bill_no draft's cases: whether the expense account is given, and dates whose due date
# ERPNext refuses, which it checks before the bill
BILL_CASES: dict[str, tuple[bool, Record]] = {
    "expense account given": (True, {}),
    "none given": (False, {}),
    "a due date before the posting date too": (
        False,
        {"set_posting_time": 1, "posting_date": "2026-11-10", "due_date": "2026-11-01"},
    ),
}


@contextmanager
def _setting(site: Site, setting: tuple[str, str]) -> Generator[None]:
    """A check of a single DocType's settings set, then cleared."""
    doctype, field = setting

    def set_to(value: int) -> None:
        site.call(
            "frappe.client.set_value", doctype=doctype, name=doctype, fieldname=field, value=value
        )

    set_to(1)
    try:
        yield
    finally:
        set_to(0)


def _messages(body: Record, account: str, draft: str) -> list[tuple[str, bool]]:
    """An error body's messages, each with its `raise_exception` mark: ERPNext's messages,
    not Enterich's text of them. HTML tags become spaces, and the expense account and the
    first draft's name placeholders, since the site's and the fake's differ."""
    return [
        (
            " ".join(re.sub(r"<[^>]*>", " ", str(m["message"])).split())
            .replace(account, "<account>")
            .replace(draft, "<draft>"),
            bool(m.get("raise_exception")),
        )
        for m in (json.loads(raw) for raw in json.loads(body["_server_messages"]))
    ]


@pytest.mark.parametrize("case", list(BILL_CASES))
def test_erpnext_refuses_a_suppliers_bill_no_twice_as_the_fake_does(
    url: str, site: Site, seeded: Seed, agent: httpx2.Client, case: str
) -> None:
    """With Accounts Settings' supplier invoice uniqueness, a second draft of the supplier's
    bill_no is refused, naming the first. Without an expense account, ERPNext sends a notice
    of the account it set for the stock item first; the refusal's message comes last, and is
    the one Enterich reports (REQ-001-PRS-F008)."""
    given, dates = BILL_CASES[case]

    def draft(account: str, **fields: Any) -> Record:
        """The draft, with the site's or the fake's Stock Received But Not Billed if given."""
        row: Record = {"item_code": seeded.item, "qty": 1, "rate": 20}
        if given:
            row["expense_account"] = account
        return {"supplier": seeded.supplier, "bill_no": "E2E-BILL-TWICE", "items": [row], **fields}

    body = draft(STOCK_NOT_BILLED)
    again = draft(STOCK_NOT_BILLED, **dates)
    with _setting(site, UNIQUENESS):
        first = _sent(_on_site(url, seeded), lambda c: c.insert("Purchase Invoice", body))
        try:
            real = _refusal(_on_site(url, seeded), lambda c: c.insert("Purchase Invoice", again))
            raw = agent.post("/api/resource/Purchase Invoice", json=again).json()
        finally:
            remove(site, [("Purchase Invoice", first["name"])])
    erp = fake.FakeErpnext(unique_bills=True, stock_items={seeded.item})
    erp.add("Supplier", fake.supplier(seeded.supplier))
    faked_body = draft(fake.STOCK_NOT_BILLED)
    faked_again = draft(fake.STOCK_NOT_BILLED, **dates)
    faked_first = _sent(_on_fake(erp), lambda c: c.insert("Purchase Invoice", faked_body))
    faked = _refusal(_on_fake(erp), lambda c: c.insert("Purchase Invoice", faked_again))
    request = httpx2.Request("POST", "http://erp/api/resource/Purchase Invoice", json=faked_again)
    faked_raw = asyncio.run(erp.handle(request)).json()
    status, exc_type, text = real
    assert faked == (status, exc_type, text.replace(first["name"], faked_first["name"]))
    assert _messages(faked_raw, fake.STOCK_NOT_BILLED, faked_first["name"]) == _messages(
        raw, STOCK_NOT_BILLED, first["name"]
    )


REPORT = "General Ledger"
LEDGER_FILTERS: Record = {"company": COMPANY, "from_date": "2026-01-01", "to_date": "2026-12-31"}
SYNC_TIMEOUT = 60.0


@contextmanager
def _report_set(field: str) -> Generator[None]:
    """The report's field set, then cleared, as the configuration guide's command does."""
    bench("frappe.db.set_value", "Report", REPORT, field, 1)
    try:
        yield
    finally:
        bench("frappe.db.set_value", "Report", REPORT, field, 0)


def _report_answers(url: str, seeded: Seed, erp: fake.FakeErpnext) -> tuple[Record, Record]:
    def run(c: Erpnext) -> Awaitable[Record]:
        return c.run_report(REPORT, LEDGER_FILTERS)

    return _sent(_on_fake(erp), run), _sent(_on_site(url, seeded), run)


def test_a_prepared_report_answers_as_the_fakes(url: str, seeded: Seed) -> None:
    """Without a run for the filters, at once: Enterich refuses rather than waiting."""
    erp = fake.FakeErpnext(prepared={REPORT})
    with _report_set("prepared_report"):
        faked, real = _report_answers(url, seeded, erp)
    assert differences(faked, [real]) == []
    assert {k: real[k] for k in faked} == faked


@pytest.fixture
def synced(site: Site) -> Iterator[None]:
    """A DuckDB sync of the GL Entries, which the report then runs on; removed afterwards."""
    sync = site.insert({"doctype": "DuckDB Sync", "doc_type": "GL Entry"})["name"]
    site.call(
        "frappe.client.submit", doc=site.call("frappe.client.get", doctype="DuckDB Sync", name=sync)
    )
    try:
        deadline = time.monotonic() + SYNC_TIMEOUT
        while site.exists("DuckDB Sync Item", {"parent": sync, "synced": 0}):
            if time.monotonic() > deadline:
                raise TimeoutError(f"Frappe's worker didn't sync {sync}.")
            time.sleep(0.5)
        # The report's table of DocTypes to sync, which no request can save on a standard
        # report; a row an interrupted run left goes first
        bench("frappe.db.delete", "Doctype To Sync", {"parent": REPORT})
        bench(
            "frappe.db.sql",
            "insert into `tabDoctype To Sync` (name, parent, parenttype, parentfield, idx, "
            "doc_type) values ('e2e-sync', %s, 'Report', 'doctype_to_sync', 1, 'GL Entry')",
            [REPORT],
        )
        try:
            yield
        finally:
            bench("frappe.db.delete", "Doctype To Sync", {"parent": REPORT})
    finally:
        site.call("frappe.client.cancel", doctype="DuckDB Sync", name=sync)
        site.delete("DuckDB Sync", sync)


def test_a_snapshot_report_answers_as_the_fakes(url: str, seeded: Seed, synced: None) -> None:
    erp = fake.FakeErpnext(snapshots={REPORT})
    with _report_set("snapshot_report"):
        faked, real = _report_answers(url, seeded, erp)
    assert differences(faked, [real]) == []
    assert real["snapshot_report"] is faked["snapshot_report"] is True
