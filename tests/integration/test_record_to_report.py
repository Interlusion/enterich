"""Record to report, the reads (REQ-006-PRS-F001, REQ-006-PRS-F002,
REQ-006-PRS-F003, REQ-006-PRS-F004): accounts, cost centres, journal entries, the General
Ledger and the Trial Balance."""

from typing import Any

import pytest

from tests.fakes.erpnext import (
    COMPANY,
    FakeErpnext,
    Received,
    account,
    balance_row,
    balance_total,
    cost_center,
    customer,
    fiscal_year,
    journal_entry,
    ledger,
    ledger_entry,
)
from tests.integration.mcp import Session

ACCOUNT_FIELDS = [
    "name",
    "account_number",
    "account_name",
    "root_type",
    "account_type",
    "parent_account",
    "is_group",
    "disabled",
]
COST_CENTER_FIELDS = [
    "name",
    "cost_center_number",
    "cost_center_name",
    "parent_cost_center",
    "is_group",
    "disabled",
]
JOURNAL_FIELDS = [
    "name",
    "voucher_type",
    "posting_date",
    "total_debit",
    "total_credit",
    "user_remark",
    "docstatus",
    "owner",
    "modified",
]
REPORT = "/api/method/frappe.desk.query_report.run"
BANK = "1200 - Bank - EX"
VOUCHER_TYPES = [
    "Journal Entry",
    "Inter Company Journal Entry",
    "Bank Entry",
    "Cash Entry",
    "Credit Card Entry",
    "Debit Note",
    "Credit Note",
    "Contra Entry",
    "Excise Entry",
    "Write Off Entry",
    "Opening Entry",
    "Depreciation Entry",
    "Asset Disposal",
    "Periodic Accounting Entry",
    "Exchange Rate Revaluation",
    "Exchange Gain Or Loss",
    "Deferred Revenue",
    "Deferred Expense",
]


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.add("Account", account(BANK))
    erpnext.add("Account", account("1000 - Assets - EX", is_group=1, parent_account=None))
    erpnext.add("Account", account("1300 - Old Bank - EX", disabled=1))
    erpnext.add("Account", account("1200 - Bank - OT", company="Other AG"))
    erpnext.add("Cost Center", cost_center("Main - EX"))
    erpnext.add("Customer", customer("CUST-0001"))
    erpnext.add("Journal Entry", journal_entry("ACC-JV-2026-00001"))
    erpnext.add("Journal Entry", journal_entry("ACC-JV-2026-00002", company="Other AG"))
    erpnext.add("Fiscal Year", fiscal_year("2026", "2026-01-01", "2026-12-31"))
    erpnext.add("Fiscal Year", fiscal_year("2025", "2025-01-01", "2025-12-31"))
    return erpnext


def report_call(erp: FakeErpnext, name: str) -> Received:
    [call] = [r for r in erp.received if r.path == REPORT]
    assert call.params["report_name"] == name
    assert call.params["are_default_filters"] == "false"
    return call


# list_accounts, list_cost_centers (REQ-006-PRS-F001)


def test_list_accounts_sends_exactly_the_catalogued_call(mcp: Session, erp: FakeErpnext) -> None:
    mcp.call("list_accounts", {"search": "1200", "root_type": "Asset"})
    [call] = erp.received
    assert (call.method, call.path) == ("GET", "/api/resource/Account")
    assert call.param("fields") == ACCOUNT_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        ["root_type", "=", "Asset"],
        ["is_group", "=", 0],
        ["disabled", "=", 0],
    ]
    assert call.param("or_filters") == [
        ["name", "like", "%1200%"],
        ["account_name", "like", "%1200%"],
        ["account_number", "like", "%1200%"],
    ]
    assert call.param("order_by") == "name asc"


def test_list_accounts_returns_the_companys_ledger_accounts(mcp: Session) -> None:
    result = mcp.call("list_accounts").data
    assert result["records"] == [
        {
            "name": BANK,
            "account_number": "1200",
            "account_name": "Bank",
            "root_type": "Asset",
            "account_type": "Bank",
            "parent_account": "1200 - Bank Accounts - EX",
            "is_group": False,
            "disabled": False,
            "outside_text": {},
        }
    ]


def test_groups_and_disabled_accounts_only_when_asked_for(mcp: Session, erp: FakeErpnext) -> None:
    result = mcp.call("list_accounts", {"include_groups": True, "include_disabled": True}).data
    assert erp.received[0].param("filters") == [["company", "=", COMPANY]]
    assert [r["name"] for r in result["records"]] == [
        "1000 - Assets - EX",
        BANK,
        "1300 - Old Bank - EX",
    ]


def test_list_cost_centers_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = mcp.call("list_cost_centers", {"search": "main"}).data
    [call] = erp.received
    assert call.path == "/api/resource/Cost Center"
    assert call.param("fields") == COST_CENTER_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        ["is_group", "=", 0],
        ["disabled", "=", 0],
    ]
    assert call.param("or_filters") == [
        ["name", "like", "%main%"],
        ["cost_center_name", "like", "%main%"],
        ["cost_center_number", "like", "%main%"],
    ]
    assert [r["name"] for r in result["records"]] == ["Main - EX"]
    assert result["records"][0]["is_group"] is False


# list_journal_entries, get_journal_entry (REQ-006-PRS-F002)


@pytest.mark.parametrize(("state", "docstatus"), [("draft", 0), ("submitted", 1), ("cancelled", 2)])
def test_list_journal_entries_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext, state: str, docstatus: int
) -> None:
    mcp.call(
        "list_journal_entries",
        {
            "state": state,
            "voucher_type": "Bank Entry",
            "from_date": "2026-10-01",
            "to_date": "2026-10-31",
        },
    )
    [call] = erp.received
    assert call.path == "/api/resource/Journal Entry"
    assert call.param("fields") == JOURNAL_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "=", docstatus],
        ["voucher_type", "=", "Bank Entry"],
        ["posting_date", ">=", "2026-10-01"],
        ["posting_date", "<=", "2026-10-31"],
    ]
    assert call.param("order_by") == "posting_date desc, name desc"


def test_list_journal_entries_returns_the_remark_as_outside_text(mcp: Session) -> None:
    result = mcp.call("list_journal_entries").data
    assert [r["name"] for r in result["records"]] == ["ACC-JV-2026-00001"]
    record = result["records"][0]
    assert record["outside_text"] == {"user_remark": "Rent October"}
    assert record["total_debit"] == 500.0


def test_every_v16_voucher_type_is_accepted_and_no_other(mcp: Session, erp: FakeErpnext) -> None:
    schema = next(t for t in mcp.tools() if t["name"] == "list_journal_entries")["inputSchema"]
    assert schema["$defs"]["VoucherType"]["enum"] == VOUCHER_TYPES
    result = mcp.call("list_journal_entries", {"voucher_type": "Payment Entry"})
    assert result.error
    assert "voucher_type" in result.text
    assert erp.received == []


def test_get_journal_entry_returns_rows_with_outside_text_apart(mcp: Session) -> None:
    result = mcp.call("get_journal_entry", {"name": "ACC-JV-2026-00001"}).data
    assert result == {
        "name": "ACC-JV-2026-00001",
        "voucher_type": "Journal Entry",
        "posting_date": "2026-10-01",
        "total_debit": 500.0,
        "total_credit": 500.0,
        "docstatus": 1,
        "owner": "bookkeeper@example.com",
        "modified": "2026-10-01 09:00:00.000000",
        "cheque_date": "2026-10-01",
        "accounts": [
            {
                "account": "6310 - Rent - EX",
                "account_currency": "EUR",
                "party_type": None,
                "party": None,
                "debit_in_account_currency": 500.0,
                "credit_in_account_currency": 0.0,
                "cost_center": "Main - EX",
                "reference_type": None,
                "reference_name": None,
                "outside_text": {"user_remark": None},
            },
            {
                "account": BANK,
                "account_currency": "EUR",
                "party_type": None,
                "party": None,
                "debit_in_account_currency": 0.0,
                "credit_in_account_currency": 500.0,
                "cost_center": "Main - EX",
                "reference_type": None,
                "reference_name": None,
                "outside_text": {"user_remark": "Paid by transfer"},
            },
        ],
        "url": "https://erp.example.com/desk/journal-entry/ACC-JV-2026-00001",
        "truncated": [],
        "outside_text": {"user_remark": "Rent October", "cheque_no": "REF-77"},
    }


def test_another_companys_journal_entry_answers_as_unknown(mcp: Session) -> None:
    other = mcp.call("get_journal_entry", {"name": "ACC-JV-2026-00002"})
    unknown = mcp.call("get_journal_entry", {"name": "ACC-JV-2026-09999"})
    assert other.error
    assert other.text.replace("00002", "") == unknown.text.replace("09999", "")
    assert other.text.startswith("name: ")


# report_general_ledger (REQ-006-PRS-F003)


def test_the_ledger_call_carries_exactly_the_fixed_filters(mcp: Session, erp: FakeErpnext) -> None:
    mcp.call("report_general_ledger", {"from_date": "2026-10-01", "to_date": "2026-10-31"})
    assert report_call(erp, "General Ledger").param("filters") == {
        "company": COMPANY,
        "from_date": "2026-10-01",
        "to_date": "2026-10-31",
        "include_default_book_entries": 1,
        "show_remarks": 1,
    }


def test_the_ledger_call_carries_the_given_inputs_as_lists(mcp: Session, erp: FakeErpnext) -> None:
    mcp.call(
        "report_general_ledger",
        {
            "from_date": "2026-10-01",
            "to_date": "2026-10-31",
            "account": BANK,
            "party_type": "Customer",
            "party": "CUST-0001",
            "voucher_no": "ACC-JV-2026-00001",
        },
    )
    account_get, party_get = [r for r in erp.received if r.path != REPORT]
    assert account_get.params == {"doctype": "Account", "name": BANK}
    assert party_get.params == {"doctype": "Customer", "name": "CUST-0001"}
    assert report_call(erp, "General Ledger").param("filters") == {
        "company": COMPANY,
        "from_date": "2026-10-01",
        "to_date": "2026-10-31",
        "account": [BANK],
        "party_type": "Customer",
        "party": ["CUST-0001"],
        "voucher_no": "ACC-JV-2026-00001",
        "include_default_book_entries": 1,
        "show_remarks": 1,
    }


def test_with_an_account_the_ledger_has_opening_balance_and_closing(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.reports["General Ledger"] = ledger(
        [
            ledger_entry("ACC-JV-2026-00001", 0.1, 0.0),
            ledger_entry("ACC-JV-2026-00002", 0.2, 0.0, posting_date="2026-10-02"),
            ledger_entry("ACC-JV-2026-00003", 0.0, 0.4, posting_date="2026-10-03"),
        ],
        opening=(1000.0, 0.0),
    )
    result = mcp.call(
        "report_general_ledger",
        {"from_date": "2026-10-01", "to_date": "2026-10-31", "account": BANK, "limit": 2},
    ).data
    assert result["opening"] == {"debit": 1000.0, "credit": 0.0, "balance": 1000.0}
    # As floats, 0.1 + 0.2 is 0.30000000000000004; Enterich sums decimals over every entry.
    assert result["totals"] == {"debit": 0.3, "credit": 0.4, "balance": -0.1}
    assert result["closing"]["balance"] == pytest.approx(999.9)
    assert result["currency"] == "EUR"
    assert (result["count"], result["has_more"]) == (2, True)
    first = result["records"][0]
    assert first == {
        "posting_date": "2026-10-01",
        "account": BANK,
        "debit": 0.1,
        "credit": 0.0,
        "balance": 1000.1,
        "voucher_type": "Journal Entry",
        "voucher_no": "ACC-JV-2026-00001",
        "party_type": None,
        "party": None,
        "outside_text": {"against": "6310 - Rent - EX", "remarks": "Rent October"},
    }


def test_without_account_or_party_the_opening_holds_the_opening_entries(
    mcp: Session, erp: FakeErpnext
) -> None:
    # ERPNext counts an Opening Entry in the opening row, not among the entries.
    erp.reports["General Ledger"] = ledger(
        [ledger_entry("ACC-JV-2026-00001", 500.0, 0.0)], opening=(70.0, 0.0)
    )
    result = mcp.call(
        "report_general_ledger", {"from_date": "2026-10-01", "to_date": "2026-10-31"}
    ).data
    assert result["opening"] == {"debit": 70.0, "credit": 0.0, "balance": 70.0}
    assert result["closing"] == {"debit": 570.0, "credit": 0.0, "balance": 570.0}
    assert result["records"][0]["balance"] is None
    assert result["totals"] == {"debit": 500.0, "credit": 0.0, "balance": 500.0}


def test_with_a_party_the_rows_carry_their_balance(mcp: Session, erp: FakeErpnext) -> None:
    erp.reports["General Ledger"] = ledger(
        [ledger_entry("ACC-SINV-2026-00001", 119.0, 0.0, party_type="Customer", party="CUST-0001")],
        opening=(10.0, 0.0),
    )
    result = mcp.call(
        "report_general_ledger",
        {
            "from_date": "2026-10-01",
            "to_date": "2026-10-31",
            "party_type": "Customer",
            "party": "CUST-0001",
        },
    ).data
    assert result["records"][0]["balance"] == 129.0


def test_amounts_in_the_accounts_currency_say_so(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Account", account("1210 - USD Bank - EX", account_currency="USD"))
    erp.reports["General Ledger"] = ledger(
        [ledger_entry("ACC-JV-2026-00001", 100.0, 0.0, account="1210 - USD Bank - EX")],
        currency="USD",
    )
    result = mcp.call(
        "report_general_ledger",
        {"from_date": "2026-10-01", "to_date": "2026-10-31", "account": "1210 - USD Bank - EX"},
    ).data
    assert result["currency"] == "USD"


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"account": "9999 - Nowhere - EX"}, "account: "),
        ({"account": "1200 - Bank - OT"}, "account: "),  # another company's
        ({"party_type": "Supplier", "party": "CUST-0001"}, "party: "),
    ],
)
def test_unknown_names_are_refused_before_the_report(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], named: str
) -> None:
    dates = {"from_date": "2026-10-01", "to_date": "2026-10-31"}
    result = mcp.call("report_general_ledger", {**dates, **arguments})
    assert result.error
    assert result.text.startswith(named)
    assert not [r for r in erp.received if r.path == REPORT]


def test_a_snapshot_ledger_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.reports["General Ledger"] = ledger([])
    erp.snapshots.add("General Ledger")
    result = mcp.call("report_general_ledger", {"from_date": "2026-10-01", "to_date": "2026-10-31"})
    assert result.error
    assert "snapshot" in result.text


def test_summary_rows_are_found_by_position_in_any_language(mcp: Session, erp: FakeErpnext) -> None:
    erp.reports["General Ledger"] = ledger(
        [ledger_entry("ACC-JV-2026-00001", 500.0, 0.0)],
        opening=(70.0, 0.0),
        labels=("Eröffnung", "Gesamt", "Abschluss (Eröffnung + Gesamt)"),
    )
    result = mcp.call(
        "report_general_ledger",
        {"from_date": "2026-10-01", "to_date": "2026-10-31", "account": BANK},
    ).data
    assert [r["voucher_no"] for r in result["records"]] == ["ACC-JV-2026-00001"]
    assert result["opening"]["debit"] == 70.0
    assert result["closing"]["debit"] == 570.0


@pytest.mark.parametrize("broken", ["first", "last"])
def test_a_ledger_without_its_summary_rows_is_a_faulty_answer(
    mcp: Session, erp: FakeErpnext, broken: str
) -> None:
    rows = ledger([ledger_entry("ACC-JV-2026-00001", 500.0, 0.0)])
    erp.reports["General Ledger"] = rows[1:] if broken == "first" else rows[:-1]
    result = mcp.call("report_general_ledger", {"from_date": "2026-10-01", "to_date": "2026-10-31"})
    assert result.error
    assert "General Ledger" in result.text


def test_a_leap_year_fits_and_a_longer_range_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.reports["General Ledger"] = ledger([])
    year = mcp.call("report_general_ledger", {"from_date": "2024-01-01", "to_date": "2024-12-31"})
    assert not year.error, year.text
    erp.received.clear()
    longer = mcp.call("report_general_ledger", {"from_date": "2026-01-01", "to_date": "2027-01-02"})
    assert longer.error
    assert "366" in longer.text
    assert erp.received == []


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"party": "CUST-0001"}, "party_type"),
        ({"party_type": "Employee", "party": "EMP-1"}, "party_type"),
        ({"to_date": "2026-09-30"}, "from_date"),
        ({"account": ["1200 - Bank - EX"]}, "account"),
    ],
)
def test_invalid_ledger_inputs_are_refused_before_erpnext(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], named: str
) -> None:
    dates = {"from_date": "2026-10-01", "to_date": "2026-10-31"}
    result = mcp.call("report_general_ledger", {**dates, **arguments})
    assert result.error
    assert named in result.text
    assert erp.received == []


def test_a_prepared_ledger_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.prepared.add("General Ledger")
    result = mcp.call("report_general_ledger", {"from_date": "2026-10-01", "to_date": "2026-10-31"})
    assert result.error
    assert "prepared report" in result.text


# report_trial_balance (REQ-006-PRS-F004)


def balances() -> list[dict[str, Any]]:
    rows = [
        balance_row("1000 - Assets - EX", None, True, opening_debit=1000.0, debit=0.3),
        balance_row(
            "1200 - Bank - EX", "1000 - Assets - EX", False, opening_debit=1000.0, debit=0.1
        ),
        balance_row("1400 - Debtors - EX", "1000 - Assets - EX", False, debit=0.2),
        balance_row("3000 - Equity - EX", None, True, opening_credit=1000.0, credit=0.3),
    ]
    return [*rows, {}, balance_total(rows)]


def test_the_trial_balance_finds_the_fiscal_year_and_sends_the_desk_defaults(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.reports["Trial Balance"] = balances()
    result = mcp.call(
        "report_trial_balance", {"from_date": "2026-01-01", "to_date": "2026-10-31"}
    ).data
    years, _ = erp.received
    assert years.path == "/api/resource/Fiscal Year"
    assert years.param("fields") == [
        "name",
        "year_start_date",
        "year_end_date",
        "companies.company",
    ]
    assert years.param("filters") == [
        ["disabled", "=", 0],
        ["year_start_date", "<=", "2026-01-01"],
        ["year_end_date", ">=", "2026-01-01"],
    ]
    assert years.param("order_by") == "year_start_date desc"
    assert years.param("limit_page_length") == "1000"
    assert report_call(erp, "Trial Balance").param("filters") == {
        "company": COMPANY,
        "fiscal_year": "2026",
        "from_date": "2026-01-01",
        "to_date": "2026-10-31",
        "show_zero_values": 0,
        "with_period_closing_entry_for_opening": 1,
        "with_period_closing_entry_for_current_period": 1,
        "include_default_book_entries": 1,
        "show_net_values": 1,
        "show_group_accounts": 1,
    }
    assert result["fiscal_year"] == "2026"


def test_trial_balance_rows_and_totals(mcp: Session, erp: FakeErpnext) -> None:
    erp.reports["Trial Balance"] = balances()
    result = mcp.call(
        "report_trial_balance",
        {"from_date": "2026-01-01", "to_date": "2026-10-31", "show_zero_values": True},
    ).data
    assert [r["account"] for r in result["records"]] == [
        "1000 - Assets - EX",
        "1200 - Bank - EX",
        "1400 - Debtors - EX",
        "3000 - Equity - EX",
    ]
    assert result["records"][1] == {
        "account": "1200 - Bank - EX",
        "account_name": "1200 - Bank",
        "parent_account": "1000 - Assets - EX",
        "is_group": False,
        "opening_debit": 1000.0,
        "opening_credit": 0.0,
        "debit": 0.1,
        "credit": 0.0,
        "closing_debit": 1000.1,
        "closing_credit": 0.0,
        "outside_text": {},
    }
    assert result["records"][0]["is_group"] is True
    # Sums of decimals over the root rows: 0.3, not ERPNext's float total.
    assert result["totals"] == {
        "opening_debit": 1000.0,
        "opening_credit": 1000.0,
        "debit": 0.3,
        "credit": 0.3,
        "closing_debit": 1000.3,
        "closing_credit": 1000.3,
    }
    assert report_call(erp, "Trial Balance").param("filters")["show_zero_values"] == 1


def test_a_year_of_the_company_comes_before_one_of_every_company(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.add("Fiscal Year", fiscal_year("2026-EX", "2026-01-01", "2026-12-31", COMPANY))
    erp.add("Fiscal Year", fiscal_year("2026-OT", "2026-01-01", "2026-12-31", "Other AG"))
    erp.reports["Trial Balance"] = balances()
    result = mcp.call(
        "report_trial_balance", {"from_date": "2026-01-01", "to_date": "2026-10-31"}
    ).data
    assert result["fiscal_year"] == "2026-EX"


def test_a_year_of_other_companies_only_doesnt_count(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Fiscal Year", fiscal_year("2027-OT", "2027-01-01", "2027-12-31", "Other AG"))
    result = mcp.call("report_trial_balance", {"from_date": "2027-01-01", "to_date": "2027-03-31"})
    assert result.error
    assert result.text.startswith("from_date:")
    assert "fiscal year" in result.text
    assert not [r for r in erp.received if r.path == REPORT]


def test_dates_in_two_fiscal_years_are_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = mcp.call("report_trial_balance", {"from_date": "2025-12-01", "to_date": "2026-01-31"})
    assert result.error
    assert result.text.startswith("to_date:")
    assert "2025" in result.text
    assert not [r for r in erp.received if r.path == REPORT]


def test_a_trial_balance_without_its_total_row_is_a_faulty_answer(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.reports["Trial Balance"] = balances()[:-2]
    result = mcp.call("report_trial_balance", {"from_date": "2026-01-01", "to_date": "2026-10-31"})
    assert result.error
    assert "Trial Balance" in result.text


def test_the_companys_year_wins_even_when_it_starts_earlier(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Fiscal Year", fiscal_year("FY-EX", "2025-07-01", "2026-06-30", COMPANY))
    erp.reports["Trial Balance"] = balances()
    result = mcp.call(
        "report_trial_balance", {"from_date": "2026-03-01", "to_date": "2026-06-30"}
    ).data
    assert result["fiscal_year"] == "FY-EX"


def test_a_fiscal_year_without_its_end_is_a_faulty_answer(mcp: Session, erp: FakeErpnext) -> None:
    # With select only, ERPNext lists a year without its non-search fields.
    erp.select_only.add("Fiscal Year")
    result = mcp.call("report_trial_balance", {"from_date": "2026-01-01", "to_date": "2026-10-31"})
    assert result.error
    assert "Fiscal Year" in result.text
    assert not [r for r in erp.received if r.path == REPORT]
