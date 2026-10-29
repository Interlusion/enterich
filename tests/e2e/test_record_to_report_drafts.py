"""Journal entry drafts end to end (REQ-006-PRS-F005 to REQ-006-PRS-F008). REQ-001's draft
rules are tested through the sales drafts; these tests show the journal entry's bodies,
its rules before ERPNext, its duplicate match and its rounding warning."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.e2e.clock import TIMEZONE, TODAY, freeze
from tests.e2e.mcp import Result, Session, client
from tests.fakes.erpnext import (
    COMPANY,
    FakeErpnext,
    Received,
    account,
    customer,
    journal_entry,
)
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import settings

PATH = "/api/resource/Journal Entry"
DRAFT = "ACC-JV-2026-00010"
MODIFIED = "2026-10-28 11:00:00.000000"
RENT = "6310 - Rent - EX"
BANK = "1200 - Bank - EX"
DEBTORS = "1400 - Debtors - EX"
PAY_RENT = [{"account": RENT, "debit": 800}, {"account": BANK, "credit": 800}]


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.add("Account", account(RENT, root_type="Expense", account_type="Expense Account"))
    erpnext.add("Account", account(BANK))
    erpnext.add("Account", account(DEBTORS, account_type="Receivable"))
    erpnext.add("Account", account("1210 - USD Bank - EX", account_currency="USD"))
    erpnext.add("Customer", customer("CUST-0001"))
    erpnext.add("Journal Entry", journal_entry("ACC-JV-2026-00001"))
    erpnext.add(
        "Journal Entry",
        journal_entry(
            DRAFT,
            docstatus=0,
            posting_date=TODAY,
            modified=MODIFIED,
            cheque_no=None,
            cheque_date=None,
        ),
    )
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext) -> Iterator[Session]:
    with client(jwks, settings(timezone=TIMEZONE), erp) as c:
        yield Session(c, token(signer))


def create(mcp: Session, **arguments: Any) -> Result:
    return mcp.call("create_draft_journal_entry", {"accounts": PAY_RENT, **arguments})


def update(mcp: Session, name: str = DRAFT, modified: str = MODIFIED, **arguments: Any) -> Result:
    return mcp.call("update_draft_journal_entry", {"name": name, "modified": modified, **arguments})


def writes(erp: FakeErpnext) -> list[Received]:
    return [r for r in erp.received if r.method in ("POST", "PUT")]


def saves(erp: FakeErpnext) -> list[Received]:
    return [r for r in writes(erp) if r.path.startswith(PATH)]


def lists(erp: FakeErpnext) -> list[Received]:
    return [r for r in erp.received if r.method == "GET" and r.path == PATH]


# create_draft_journal_entry (REQ-006-PRS-F005)


def test_a_create_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    rows = [
        {
            "account": BANK,
            "debit": 119,
            "cost_center": "Main - EX",
            "user_remark": "Transfer of 2 Nov",
        },
        {
            "account": DEBTORS,
            "credit": 119,
            "party_type": "Customer",
            "party": "CUST-0001",
            "reference_type": "Sales Invoice",
            "reference_name": "ACC-SINV-2026-00001",
        },
    ]
    result = create(
        mcp,
        posting_date="2026-11-02",
        cheque_no="TX-4711",
        cheque_date="2026-11-02",
        user_remark="Payment of ACC-SINV-2026-00001",
        accounts=rows,
    )
    assert not result.error, result.text
    [post] = saves(erp)
    assert (post.method, post.path) == ("POST", PATH)
    assert post.body == {
        "posting_date": "2026-11-02",
        "cheque_no": "TX-4711",
        "cheque_date": "2026-11-02",
        "user_remark": "Payment of ACC-SINV-2026-00001",
        "accounts": [
            {
                "account": BANK,
                "debit_in_account_currency": 119,
                "cost_center": "Main - EX",
                "user_remark": "Transfer of 2 Nov",
            },
            {
                "account": DEBTORS,
                "credit_in_account_currency": 119,
                "party_type": "Customer",
                "party": "CUST-0001",
                "reference_type": "Sales Invoice",
                "reference_name": "ACC-SINV-2026-00001",
            },
        ],
        "voucher_type": "Journal Entry",
        "multi_currency": 0,
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_create_without_a_posting_date_sends_today(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp)
    assert not result.error, result.text
    [post] = saves(erp)
    assert post.body == {
        "posting_date": TODAY,
        "accounts": [
            {"account": RENT, "debit_in_account_currency": 800},
            {"account": BANK, "credit_in_account_currency": 800},
        ],
        "voucher_type": "Journal Entry",
        "multi_currency": 0,
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_create_returns_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp).data
    name = result["name"]
    assert name.startswith("ACC-JV-")
    assert result == {
        "name": name,
        "modified": erp.docs["Journal Entry"][name]["modified"],
        "docstatus": 0,
        "company": COMPANY,
        "posting_date": TODAY,
        "total_debit": 800,
        "total_credit": 800,
        "row_count": 2,
        "url": f"https://erp.example.com/desk/journal-entry/{name}",
        "warnings": [],
        "truncated": [],
        "outside_text": {},
    }


def test_the_create_says_how_to_retry(mcp: Session) -> None:
    tools = {t["name"]: t for t in mcp.tools()}
    description = tools["create_draft_journal_entry"]["description"]
    assert "`list_journal_entries` with `state` draft" in description


# The rules before ERPNext (REQ-006-PRS-F006)


ONE_SIDE = "accounts.0: Value error, give exactly one of debit and credit, above 0"
PARTY = "accounts.0: Value error, party_type and party come together"
REFERENCE = "accounts.0: Value error, reference_type and reference_name come together"


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"accounts": [{"account": RENT, "debit": 1, "credit": 1}, PAY_RENT[1]]}, ONE_SIDE),
        ({"accounts": [{"account": RENT}, PAY_RENT[1]]}, ONE_SIDE),
        ({"accounts": [{"account": RENT, "debit": 0}, PAY_RENT[1]]}, ONE_SIDE),
        (
            {"accounts": [{"account": RENT, "debit": 799.99}, PAY_RENT[1]]},
            "accounts: Value error, the debits (799.99) and the credits (800) must be equal",
        ),
        ({"accounts": [{**PAY_RENT[0], "party": "CUST-0001"}, PAY_RENT[1]]}, PARTY),
        ({"accounts": [{**PAY_RENT[0], "party_type": "Customer"}, PAY_RENT[1]]}, PARTY),
        ({"accounts": [{**PAY_RENT[0], "reference_name": "X"}, PAY_RENT[1]]}, REFERENCE),
        (
            {"accounts": [{**PAY_RENT[0], "reference_type": "Sales Invoice"}, PAY_RENT[1]]},
            REFERENCE,
        ),
        (
            {"accounts": [{**PAY_RENT[0], "party_type": "Employee", "party": "E"}, PAY_RENT[1]]},
            "accounts.0.party_type: ",
        ),
        ({"accounts": [{**PAY_RENT[0], "debit": 800.0001}, PAY_RENT[1]]}, "accounts.0.debit: "),
        ({"accounts": PAY_RENT[:1]}, "accounts: List should have at least 2 items"),
        ({"accounts": PAY_RENT * 11}, "accounts: List should have at most 20 items"),
        ({"cheque_no": "TX-1"}, "cheque_date: a reference number (cheque_no) needs its date"),
        (
            {"cheque_date": "2026-11-02"},
            "cheque_no: a reference date (cheque_date) needs its number",
        ),
        ({"voucher_type": "Bank Entry"}, "voucher_type: Extra inputs are not permitted"),
        (
            {"accounts": [{**PAY_RENT[0], "debit_in_account_currency": 800}, PAY_RENT[1]]},
            "accounts.0.debit_in_account_currency: Extra inputs are not permitted",
        ),
    ],
)
def test_a_broken_rule_is_refused_before_erpnext(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = create(mcp, **arguments)
    assert result.error
    assert says in result.text
    assert erp.received == []


def test_debits_and_credits_balance_as_exact_decimals(mcp: Session) -> None:
    # As floats, 0.1 + 0.2 isn't 0.3.
    rows = [
        {"account": RENT, "debit": 0.1},
        {"account": RENT, "debit": 0.2},
        {"account": BANK, "credit": 0.3},
    ]
    result = create(mcp, accounts=rows)
    assert not result.error, result.text


@pytest.mark.parametrize(
    ("rows", "says"),
    [
        (
            [{"account": "1210 - USD Bank - EX", "debit": 800}, PAY_RENT[1]],
            "Multi Currency",
        ),
        ([{"account": DEBTORS, "debit": 800}, PAY_RENT[1]], "Party Type and Party is required"),
    ],
)
def test_erpnexts_refusals_reach_the_agent(
    mcp: Session, rows: list[dict[str, Any]], says: str
) -> None:
    result = create(mcp, accounts=rows)
    assert result.error
    assert says in result.text


# Duplicates (REQ-006-PRS-F007)


def test_the_duplicate_check_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext
) -> None:
    create(mcp, posting_date="2026-11-02")
    [check] = lists(erp)
    assert check.param("fields") == [
        "name",
        "accounts.account",
        "accounts.debit_in_account_currency",
        "accounts.credit_in_account_currency",
    ]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "=", 0],
        ["posting_date", "=", "2026-11-02"],
    ]


def test_a_create_with_the_drafts_rows_is_refused_naming_it(mcp: Session, erp: FakeErpnext) -> None:
    # The fixture draft: rent 500 against the bank, today; given in another order.
    rows = [{"account": BANK, "credit": 500}, {"account": RENT, "debit": 500}]
    result = create(mcp, accounts=rows)
    assert result.error
    assert result.text.startswith("allow_duplicate:")
    assert DRAFT in result.text
    assert writes(erp) == []


@pytest.mark.parametrize(
    "arguments",
    [
        {"accounts": [{"account": RENT, "debit": 501}, {"account": BANK, "credit": 501}]},
        {
            "accounts": [{"account": RENT, "debit": 500}, {"account": BANK, "credit": 500}],
            "posting_date": "2026-11-02",
        },
    ],
)
def test_a_create_differing_in_a_row_or_the_date_goes_through(
    mcp: Session, arguments: dict[str, Any]
) -> None:
    result = create(mcp, **arguments)
    assert not result.error, result.text
    assert result.data["warnings"] == []


def test_a_repeated_create_matches_the_amounts_erpnext_rounded(
    mcp: Session, erp: FakeErpnext
) -> None:
    rows = [{"account": RENT, "debit": 100.004}, {"account": BANK, "credit": 100.004}]
    first = create(mcp, accounts=rows).data
    assert erp.docs["Journal Entry"][first["name"]]["total_debit"] == 100.0
    again = create(mcp, accounts=rows)
    assert again.error
    assert again.text.startswith("allow_duplicate:")
    assert first["name"] in again.text
    assert len(saves(erp)) == 1


def test_allow_duplicate_creates_and_says_so(mcp: Session, erp: FakeErpnext) -> None:
    rows = [{"account": RENT, "debit": 500}, {"account": BANK, "credit": 500}]
    result = create(mcp, accounts=rows, allow_duplicate=True).data
    [warning] = result["warnings"]
    assert DRAFT in warning
    [comment] = erp.comments
    assert comment["reference_doctype"] == "Journal Entry"


# Rounding (REQ-006-PRS-F008)


def test_totals_erpnext_rounded_apart_warn(mcp: Session, erp: FakeErpnext) -> None:
    rows = [
        {"account": RENT, "debit": 10.004},
        {"account": RENT, "debit": 5.004},
        {"account": BANK, "credit": 15.008},
    ]
    result = create(mcp, accounts=rows).data
    assert (result["total_debit"], result["total_credit"]) == (15.0, 15.01)
    assert result["warnings"] == [
        "ERPNext rounded the rows to the currency's precision and saved a total debit of 15 "
        "against a total credit of 15.01; adjust the rows so that they balance, or ERPNext "
        "refuses to submit the entry."
    ]
    assert len(erp.comments) == 1


# update_draft_journal_entry


def test_an_update_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    rows = [
        {"account": RENT, "debit": 650, "cost_center": "Main - EX"},
        {"account": BANK, "credit": 650},
    ]
    result = update(
        mcp,
        posting_date="2026-11-02",
        cheque_no="TX-4712",
        cheque_date="2026-11-01",
        user_remark="Rent November",
        accounts=rows,
    )
    assert not result.error, result.text
    [put] = saves(erp)
    assert (put.method, put.path) == ("PUT", f"{PATH}/{DRAFT}")
    assert put.body == {
        "posting_date": "2026-11-02",
        "cheque_no": "TX-4712",
        "cheque_date": "2026-11-01",
        "user_remark": "Rent November",
        "accounts": [
            {"account": RENT, "debit_in_account_currency": 650, "cost_center": "Main - EX"},
            {"account": BANK, "credit_in_account_currency": 650},
        ],
        "modified": MODIFIED,
    }


def test_clearing_the_reference_clears_its_date(mcp: Session, erp: FakeErpnext) -> None:
    dated = update(mcp, cheque_no="TX-1", cheque_date="2026-10-28").data
    result = update(mcp, modified=dated["modified"], cheque_no="", user_remark="")
    assert not result.error, result.text
    put = saves(erp)[-1]
    assert put.body == {
        "cheque_no": "",
        "cheque_date": None,
        "user_remark": "",
        "modified": dated["modified"],
    }


def test_a_date_for_a_draft_with_a_reference_goes_through(mcp: Session, erp: FakeErpnext) -> None:
    dated = update(mcp, cheque_no="TX-1", cheque_date="2026-10-28").data
    result = update(mcp, modified=dated["modified"], cheque_date="2026-10-27")
    assert not result.error, result.text


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"cheque_date": "2026-10-27"}, "cheque_no: a reference date (cheque_date) needs its"),
        ({"cheque_no": "TX-2"}, "cheque_date: a reference number (cheque_no) needs its date"),
        (
            {"accounts": [{"account": RENT, "debit": 1}, {"account": BANK, "credit": 2}]},
            "accounts: Value error, the debits (1) and the credits (2) must be equal",
        ),
        ({"cheque_date": ""}, "cheque_date: "),
        ({"accounts": []}, "accounts: List should have at least 2 items"),
        ({}, "give at least one of posting_date, cheque_no, cheque_date, user_remark, accounts"),
    ],
)
def test_an_update_breaking_a_rule_is_refused_before_a_write(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = update(mcp, **arguments)
    assert result.error
    assert says in result.text
    assert writes(erp) == []


def test_an_update_without_rows_needs_the_drafts_rows_to_balance(
    mcp: Session, erp: FakeErpnext
) -> None:
    # A person saved it unbalanced; ERPNext checks the balance only on submit.
    erp.docs["Journal Entry"][DRAFT].update(total_debit=500.0, total_credit=499.5)
    result = update(mcp, user_remark="Changed")
    assert result.error
    assert result.text == (
        "accounts: the draft's rows don't balance (total debit 500 against total credit "
        "499.5); give the rows."
    )
    assert writes(erp) == []
    rows = [{"account": RENT, "debit": 500}, {"account": BANK, "credit": 500}]
    assert not update(mcp, accounts=rows).error


def test_a_drafts_date_without_a_number_says_how_to_clear_it(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Journal Entry"][DRAFT]["cheque_date"] = "2026-10-20"
    result = update(mcp, user_remark="Changed")
    assert result.error
    assert result.text == (
        "cheque_no: the draft has a reference date (2026-10-20) without a reference number; "
        "give cheque_no, or an empty cheque_no to clear the date."
    )
    assert writes(erp) == []
    assert not update(mcp, cheque_no="").error


@pytest.mark.parametrize(
    "overrides",
    [
        {"voucher_type": "Bank Entry"},
        {"voucher_type": "Opening Entry"},
        {"voucher_type": "Bank Entry", "docstatus": 1},
        {"company": "Other AG"},
        {"company": "Other AG", "docstatus": 1},
    ],
)
def test_what_erpel_doesnt_change_answers_as_unknown(
    mcp: Session, erp: FakeErpnext, overrides: dict[str, Any]
) -> None:
    other = journal_entry("ACC-JV-2026-00012", **{"docstatus": 0, **overrides})
    erp.add("Journal Entry", other)
    # Stale as well: the answer comes before the state and `modified` are checked.
    result = update(mcp, "ACC-JV-2026-00012", "2026-01-01 00:00:00.000000", user_remark="X")
    unknown = update(mcp, "ACC-JV-2026-09999", user_remark="X")
    assert result.error
    assert result.text.startswith("name: ")
    assert result.text.replace("00012", "") == unknown.text.replace("09999", "")
    assert writes(erp) == []


def test_a_multi_currency_draft_isnt_changed(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Journal Entry"][DRAFT]["multi_currency"] = 1
    result = update(mcp, user_remark="Changed")
    assert result.error
    assert result.text == (
        f"name: {DRAFT} has accounts in several currencies; Erpel changes only journal "
        "entries in the company's currency."
    )
    assert writes(erp) == []


def test_only_drafts_can_be_updated(mcp: Session, erp: FakeErpnext) -> None:
    stored = erp.docs["Journal Entry"]["ACC-JV-2026-00001"]
    result = update(mcp, "ACC-JV-2026-00001", stored["modified"], user_remark="Changed")
    assert result.error
    assert "submitted" in result.text
    assert writes(erp) == []


def test_a_stale_update_changes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, modified="2026-10-28 10:00:00.000000", user_remark="Changed")
    assert result.error
    assert "changed" in result.text
    assert writes(erp) == []


def test_an_update_warns_where_totals_were_rounded_apart(mcp: Session, erp: FakeErpnext) -> None:
    rows = [
        {"account": RENT, "debit": 10.004},
        {"account": RENT, "debit": 5.004},
        {"account": BANK, "credit": 15.008},
    ]
    result = update(mcp, accounts=rows).data
    [warning] = result["warnings"]
    assert "total debit of 15 against a total credit of 15.01;" in warning
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT


def test_a_draft_without_rows_matches_nothing(mcp: Session, erp: FakeErpnext) -> None:
    empty = journal_entry("ACC-JV-2026-00012", docstatus=0, posting_date=TODAY, accounts=[])
    erp.add("Journal Entry", empty)
    result = create(mcp)
    assert not result.error, result.text
    assert result.data["warnings"] == []
