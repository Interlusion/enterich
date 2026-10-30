"""Record to report against the seeded site: accounts, cost centres, journal entries, and
the General Ledger and Trial Balance with the catalogues' filters and columns
(REQ-006-PRS-F001 to REQ-006-PRS-F004)."""

from decimal import Decimal

from tests.e2e.seed import BANK_GROUP, CAPITAL, DEBTORS, SALES_VAT, Seed
from tests.integration.mcp import Session


def year(seeded: Seed) -> dict[str, str]:
    y = seeded.posted.year
    return {"from_date": f"{y}-01-01", "to_date": f"{y}-12-31"}


def test_list_accounts(mcp: Session, seeded: Seed) -> None:
    records = mcp.call("list_accounts", {"search": "Debtors"}).data["records"]
    assert [
        (r["name"], r["account_number"], r["account_type"], r["root_type"]) for r in records
    ] == [(DEBTORS, "1310", "Receivable", "Asset")]


def test_list_accounts_by_root_type_with_groups(mcp: Session, seeded: Seed) -> None:
    records = mcp.call(
        "list_accounts", {"root_type": "Asset", "include_groups": True, "search": "Bank"}
    ).data["records"]
    assert {(r["name"], r["is_group"]) for r in records} >= {
        (BANK_GROUP, True),
        (seeded.bank_ledger, False),
    }


def test_list_cost_centers(mcp: Session, seeded: Seed) -> None:
    ledgers = mcp.call("list_cost_centers", {}).data["records"]
    assert ("Main - EX", "Example GmbH - EX", False) in [
        (r["name"], r["parent_cost_center"], r["is_group"]) for r in ledgers
    ]
    groups = mcp.call("list_cost_centers", {"include_groups": True}).data["records"]
    assert "Example GmbH - EX" in [r["name"] for r in groups]


def test_list_journal_entries_with_every_filter(mcp: Session, seeded: Seed) -> None:
    day = seeded.posted.isoformat()
    records = mcp.call(
        "list_journal_entries",
        {"state": "submitted", "voucher_type": "Bank Entry", "from_date": day, "to_date": day},
    ).data["records"]
    assert [(r["name"], r["total_debit"], r["total_credit"]) for r in records] == [
        (seeded.journal_entry, 1000, 1000)
    ]
    assert records[0]["outside_text"] == {"user_remark": "Capital paid in"}


def test_get_journal_entry_with_its_rows(mcp: Session, seeded: Seed) -> None:
    entry = mcp.call("get_journal_entry", {"name": seeded.journal_entry}).data
    assert entry["cheque_date"] == seeded.posted.isoformat()
    assert entry["outside_text"]["cheque_no"] == "SEED-JE-1"
    rows = [
        (r["account"], r["debit_in_account_currency"], r["credit_in_account_currency"])
        for r in entry["accounts"]
    ]
    assert rows == [(seeded.bank_ledger, 1000, 0), (CAPITAL, 0, 1000)]


def test_general_ledger_of_a_voucher(mcp: Session, seeded: Seed) -> None:
    report = mcp.call(
        "report_general_ledger", {**year(seeded), "voucher_no": seeded.sales_invoice}
    ).data
    rows = {(r["account"], r["debit"], r["credit"]) for r in report["records"]}
    assert rows == {
        (DEBTORS, 119, 0),
        (SALES_VAT[1], 0, 19),
        ("4110 - Sales - EX", 0, 100),
    }
    # Without an account or a party, no running balance
    assert {r["balance"] for r in report["records"]} == {None}
    assert report["totals"] == {"debit": 119, "credit": 119, "balance": 0}
    assert report["currency"] == "EUR"


def test_general_ledger_of_an_account_runs_its_balance(mcp: Session, seeded: Seed) -> None:
    report = mcp.call("report_general_ledger", {**year(seeded), "account": seeded.bank_ledger}).data
    records = report["records"]
    assert {r["voucher_no"] for r in records} == {seeded.payment_entry, seeded.journal_entry}
    assert records[-1]["balance"] == 1050
    assert report["opening"] == {"debit": 0, "credit": 0, "balance": 0}
    assert report["closing"] == {"debit": 1050, "credit": 0, "balance": 1050}


def test_general_ledger_of_a_party(mcp: Session, seeded: Seed) -> None:
    report = mcp.call(
        "report_general_ledger",
        {**year(seeded), "party_type": "Customer", "party": seeded.customer},
    ).data
    # Both posted on one day; their order there is ERPNext's to choose
    assert {(r["voucher_no"], r["debit"], r["credit"]) for r in report["records"]} == {
        (seeded.sales_invoice, 119, 0),
        (seeded.payment_entry, 0, 50),
    }
    assert report["records"][-1]["balance"] == report["closing"]["balance"] == 69


def test_trial_balance_of_the_year(mcp: Session, seeded: Seed) -> None:
    report = mcp.call("report_trial_balance", {**year(seeded), "limit": 100}).data
    assert report["fiscal_year"] == str(seeded.posted.year)
    assert not report["has_more"]
    accounts = {r["account"]: r for r in report["records"]}
    bank = accounts[seeded.bank_ledger]
    assert (bank["is_group"], bank["debit"], bank["closing_debit"]) == (False, 1050, 1050)
    assert accounts[BANK_GROUP]["is_group"] is True
    totals = {k: Decimal(str(v)) for k, v in report["totals"].items()}
    assert totals["debit"] == totals["credit"] > 0
    assert totals["closing_debit"] == totals["closing_credit"]


def test_trial_balance_shows_accounts_without_values_when_asked(mcp: Session, seeded: Seed) -> None:
    def accounts(show: bool) -> set[str]:
        """Every page: with zero values, the chart has more accounts than one holds."""
        found: set[str] = set()
        offset, more = 0, True
        while more:
            args = {**year(seeded), "show_zero_values": show, "limit": 100, "offset": offset}
            report = mcp.call("report_trial_balance", args).data
            found |= {r["account"] for r in report["records"]}
            offset, more = offset + 100, report["has_more"]
        return found

    without, with_zero = accounts(False), accounts(True)
    assert without < with_zero
    assert "3200 - Dividends Paid - EX" in with_zero - without
