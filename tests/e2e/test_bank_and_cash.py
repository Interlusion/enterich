"""Bank and cash end to end (REQ-007-PRS-F001 to REQ-007-PRS-F003): the company's bank
accounts, its bank transactions and its payment entries."""

from collections.abc import Iterator
from typing import Any

import pytest

from tests.e2e.clock import TIMEZONE, freeze
from tests.e2e.mcp import Session, client
from tests.fakes.erpnext import (
    COMPANY,
    FakeErpnext,
    bank_account,
    bank_transaction,
    payment_entry,
)
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import settings

BANK_ACCOUNT_FIELDS = [
    "name",
    "account_name",
    "bank",
    "account",
    "iban",
    "bank_account_no",
    "is_default",
    "disabled",
]
TRANSACTION_FIELDS = [
    "name",
    "date",
    "bank_account",
    "deposit",
    "withdrawal",
    "included_fee",
    "currency",
    "unallocated_amount",
    "status",
    "party_type",
    "party",
    "description",
    "reference_number",
    "transaction_type",
    "bank_party_name",
    "bank_party_iban",
    "bank_party_account_number",
]
PAYMENT_FIELDS = [
    "name",
    "payment_type",
    "posting_date",
    "party_type",
    "party",
    "party_name",
    "paid_amount",
    "received_amount",
    "paid_from_account_currency",
    "paid_to_account_currency",
    "mode_of_payment",
    "reference_no",
    "reference_date",
    "bank_account",
    "unallocated_amount",
    "clearance_date",
    "docstatus",
    "modified",
]
MAIN = "Main - Example Bank"
TRANSACTION = "ACC-BTN-2026-00001"
PENDING = "ACC-BTN-2026-00002"
PAYMENT = "ACC-PAY-2026-00001"


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.add("Bank Account", bank_account(MAIN))
    erpnext.add("Bank Account", bank_account("Old - Example Bank", is_default=0, disabled=1))
    # A customer's account, kept under the same company
    erpnext.add(
        "Bank Account",
        bank_account(
            "CUST-0001 - Other Bank",
            is_company_account=0,
            is_default=0,
            party_type="Customer",
            party="CUST-0001",
        ),
    )
    erpnext.add("Bank Account", bank_account("Main - Other Bank", company="Other AG"))
    erpnext.add("Bank Transaction", bank_transaction(TRANSACTION))
    erpnext.add(
        "Bank Transaction",
        bank_transaction(
            PENDING,
            date="2026-10-21",
            status="Pending",
            docstatus=0,
            allocated_amount=0.0,
            unallocated_amount=119.0,
            payment_entries=[],
        ),
    )
    erpnext.add(
        "Bank Transaction",
        bank_transaction(
            "ACC-BTN-2026-00003",
            date="2026-10-19",
            status="Reconciled",
            allocated_amount=119.0,
            unallocated_amount=0.0,
        ),
    )
    erpnext.add(
        "Bank Transaction",
        bank_transaction("ACC-BTN-2026-00004", date="2026-10-18", status="Cancelled", docstatus=2),
    )
    erpnext.add("Bank Transaction", bank_transaction("ACC-BTN-2026-00005", company="Other AG"))
    erpnext.add("Payment Entry", payment_entry(PAYMENT))
    erpnext.add("Payment Entry", payment_entry("ACC-PAY-2026-00002", company="Other AG"))
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext) -> Iterator[Session]:
    with client(jwks, settings(timezone=TIMEZONE), erp) as c:
        yield Session(c, token(signer))


# list_bank_accounts (REQ-007-PRS-F001)


def test_list_bank_accounts_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext
) -> None:
    mcp.call("list_bank_accounts", {"limit": 5, "offset": 5})
    [call] = erp.received
    assert (call.method, call.path) == ("GET", "/api/resource/Bank Account")
    assert call.param("fields") == BANK_ACCOUNT_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        ["is_company_account", "=", 1],
        ["disabled", "=", 0],
    ]
    assert call.param("order_by") == "name asc"
    assert (call.param("limit_start"), call.param("limit_page_length")) == ("5", "6")


def test_list_bank_accounts_returns_only_the_companys_own(mcp: Session) -> None:
    result = mcp.call("list_bank_accounts").data
    assert result["records"] == [
        {
            "name": MAIN,
            "account_name": "Main",
            "bank": "Example Bank",
            "account": "1200 - Bank - EX",
            "iban": "DE02120300000000202051",
            "bank_account_no": None,
            "is_default": True,
            "disabled": False,
            "outside_text": {},
        }
    ]


def test_disabled_bank_accounts_only_when_asked_for(mcp: Session, erp: FakeErpnext) -> None:
    result = mcp.call("list_bank_accounts", {"include_disabled": True}).data
    assert erp.received[0].param("filters") == [
        ["company", "=", COMPANY],
        ["is_company_account", "=", 1],
    ]
    assert [r["name"] for r in result["records"]] == [MAIN, "Old - Example Bank"]


# list_bank_transactions, get_bank_transaction (REQ-007-PRS-F002)


@pytest.mark.parametrize(
    ("state", "filters"),
    [
        (None, [["docstatus", "=", 1], ["unallocated_amount", ">", 0]]),
        ("unreconciled", [["docstatus", "=", 1], ["unallocated_amount", ">", 0]]),
        ("reconciled", [["docstatus", "=", 1], ["unallocated_amount", "<=", 0]]),
        ("pending", [["docstatus", "=", 0]]),
        ("all", [["docstatus", "<", 2]]),
    ],
)
def test_list_bank_transactions_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext, state: str | None, filters: list[list[Any]]
) -> None:
    arguments: dict[str, Any] = {
        "bank_account": MAIN,
        "from_date": "2026-10-01",
        "to_date": "2026-10-31",
    }
    if state is not None:
        arguments["state"] = state
    mcp.call("list_bank_transactions", arguments)
    [call] = erp.received
    assert (call.method, call.path) == ("GET", "/api/resource/Bank Transaction")
    assert call.param("fields") == TRANSACTION_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        *filters,
        ["bank_account", "=", MAIN],
        ["date", ">=", "2026-10-01"],
        ["date", "<=", "2026-10-31"],
    ]
    assert call.param("order_by") == "date desc, name desc"


@pytest.mark.parametrize(
    ("state", "names"),
    [
        (None, [TRANSACTION]),
        ("unreconciled", [TRANSACTION]),
        ("reconciled", ["ACC-BTN-2026-00003"]),
        ("pending", [PENDING]),
        ("all", [PENDING, TRANSACTION, "ACC-BTN-2026-00003"]),
    ],
)
def test_each_state_returns_its_transactions(
    mcp: Session, state: str | None, names: list[str]
) -> None:
    arguments = {} if state is None else {"state": state}
    result = mcp.call("list_bank_transactions", arguments).data
    assert [r["name"] for r in result["records"]] == names


def test_list_bank_transactions_returns_the_banks_texts_as_outside_text(mcp: Session) -> None:
    [record] = mcp.call("list_bank_transactions").data["records"]
    assert record == {
        "name": TRANSACTION,
        "date": "2026-10-20",
        "bank_account": MAIN,
        "deposit": 119.0,
        "withdrawal": 0.0,
        "included_fee": 0.0,
        "currency": "EUR",
        "unallocated_amount": 100.0,
        "status": "Unreconciled",
        "party_type": "Customer",
        "party": "CUST-0001",
        "outside_text": {
            "description": "Invoice ACC-SINV-2026-00001, thank you",
            "reference_number": "NOTPROVIDED",
            "transaction_type": "SEPA credit transfer",
            "bank_party_name": "Customer CUST-0001",
            "bank_party_iban": "DE89370400440532013000",
            "bank_party_account_number": None,
        },
    }


def test_get_bank_transaction_returns_its_allocations(mcp: Session) -> None:
    result = mcp.call("get_bank_transaction", {"name": TRANSACTION}).data
    assert result == {
        "name": TRANSACTION,
        "date": "2026-10-20",
        "bank_account": MAIN,
        "deposit": 119.0,
        "withdrawal": 0.0,
        "included_fee": 0.0,
        "currency": "EUR",
        "unallocated_amount": 100.0,
        "status": "Unreconciled",
        "party_type": "Customer",
        "party": "CUST-0001",
        "modified": "2026-10-20 09:00:00.000000",
        "payment_entries": [
            {
                "payment_document": "Payment Entry",
                "payment_entry": PAYMENT,
                "allocated_amount": 19.0,
                "outside_text": {},
            }
        ],
        "url": f"https://erp.example.com/desk/bank-transaction/{TRANSACTION}",
        "truncated": [],
        "outside_text": {
            "description": "Invoice ACC-SINV-2026-00001, thank you",
            "reference_number": "NOTPROVIDED",
            "transaction_type": "SEPA credit transfer",
            "bank_party_name": "Customer CUST-0001",
            "bank_party_iban": "DE89370400440532013000",
            "bank_party_account_number": None,
        },
    }


def test_a_long_description_is_cut_and_named(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Bank Transaction"][TRANSACTION]["description"] = "x" * 600
    result = mcp.call("get_bank_transaction", {"name": TRANSACTION}).data
    assert len(result["outside_text"]["description"]) == 500
    assert result["truncated"] == ["description"]


def test_get_bank_transaction_cuts_its_allocations_at_100(mcp: Session, erp: FakeErpnext) -> None:
    stored = erp.docs["Bank Transaction"][TRANSACTION]
    stored["payment_entries"] = stored["payment_entries"] * 101
    result = mcp.call("get_bank_transaction", {"name": TRANSACTION}).data
    assert len(result["payment_entries"]) == 100
    assert result["truncated"] == ["payment_entries"]


def test_another_companys_bank_transaction_answers_as_unknown(mcp: Session) -> None:
    other = mcp.call("get_bank_transaction", {"name": "ACC-BTN-2026-00005"})
    unknown = mcp.call("get_bank_transaction", {"name": "ACC-BTN-2026-09999"})
    assert other.error
    assert other.text.startswith("name: ")
    assert other.text.replace("00005", "") == unknown.text.replace("09999", "")


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"state": "draft"}, "state: "),
        ({"from_date": "2026-10-31", "to_date": "2026-10-01"}, "from_date"),
    ],
)
def test_a_bank_transaction_list_breaking_a_rule_is_refused(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = mcp.call("list_bank_transactions", arguments)
    assert result.error
    assert says in result.text
    assert erp.received == []


# list_payment_entries, get_payment_entry (REQ-007-PRS-F003)


@pytest.mark.parametrize(("state", "docstatus"), [("draft", 0), ("submitted", 1), ("cancelled", 2)])
def test_list_payment_entries_sends_exactly_the_catalogued_call(
    mcp: Session, erp: FakeErpnext, state: str, docstatus: int
) -> None:
    mcp.call(
        "list_payment_entries",
        {
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": "CUST-0001",
            "state": state,
            "from_date": "2026-10-01",
            "to_date": "2026-10-31",
        },
    )
    [call] = erp.received
    assert (call.method, call.path) == ("GET", "/api/resource/Payment Entry")
    assert call.param("fields") == PAYMENT_FIELDS
    assert call.param("filters") == [
        ["company", "=", COMPANY],
        ["payment_type", "=", "Receive"],
        ["party_type", "=", "Customer"],
        ["party", "=", "CUST-0001"],
        ["docstatus", "=", docstatus],
        ["posting_date", ">=", "2026-10-01"],
        ["posting_date", "<=", "2026-10-31"],
    ]
    assert call.param("order_by") == "posting_date desc, name desc"


def test_list_payment_entries_without_inputs_filters_by_company_only(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = mcp.call("list_payment_entries").data
    assert erp.received[0].param("filters") == [["company", "=", COMPANY]]
    assert [r["name"] for r in result["records"]] == [PAYMENT]
    assert result["records"][0]["outside_text"] == {
        "party_name": "Customer CUST-0001",
        "reference_no": "TX-4711",
    }


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"party": "CUST-0001"}, "party needs party_type"),
        ({"party_type": "Employee"}, "party_type: "),
        ({"payment_type": "Transfer"}, "payment_type: "),
        ({"state": "unreconciled"}, "state: "),
    ],
)
def test_a_payment_entry_list_breaking_a_rule_is_refused(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = mcp.call("list_payment_entries", arguments)
    assert result.error
    assert says in result.text
    assert erp.received == []


def test_get_payment_entry_returns_its_references(mcp: Session) -> None:
    result = mcp.call("get_payment_entry", {"name": PAYMENT}).data
    assert result == {
        "name": PAYMENT,
        "payment_type": "Receive",
        "posting_date": "2026-10-20",
        "party_type": "Customer",
        "party": "CUST-0001",
        "paid_amount": 19.0,
        "received_amount": 19.0,
        "paid_from_account_currency": "EUR",
        "paid_to_account_currency": "EUR",
        "mode_of_payment": "Wire Transfer",
        "reference_date": "2026-10-20",
        "bank_account": MAIN,
        "unallocated_amount": 0.0,
        "clearance_date": None,
        "docstatus": 1,
        "modified": "2026-10-20 09:30:00.000000",
        "paid_from": "1400 - Debtors - EX",
        "paid_to": "1200 - Bank - EX",
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": "ACC-SINV-2026-00001",
                "allocated_amount": 19.0,
                "outside_text": {},
            }
        ],
        "url": f"https://erp.example.com/desk/payment-entry/{PAYMENT}",
        "truncated": [],
        "outside_text": {
            "party_name": "Customer CUST-0001",
            "reference_no": "TX-4711",
            "remarks": "Amount EUR 19 received from CUST-0001",
        },
    }


def test_get_payment_entry_cuts_its_references_at_100(mcp: Session, erp: FakeErpnext) -> None:
    stored = erp.docs["Payment Entry"][PAYMENT]
    stored["references"] = stored["references"] * 101
    result = mcp.call("get_payment_entry", {"name": PAYMENT}).data
    assert len(result["references"]) == 100
    assert result["truncated"] == ["references"]


def test_another_companys_payment_entry_answers_as_unknown(mcp: Session) -> None:
    other = mcp.call("get_payment_entry", {"name": "ACC-PAY-2026-00002"})
    unknown = mcp.call("get_payment_entry", {"name": "ACC-PAY-2026-09999"})
    assert other.error
    assert other.text.startswith("name: ")
    assert other.text.replace("00002", "") == unknown.text.replace("09999", "")
