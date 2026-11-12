"""Payment entry drafts (REQ-007-PRS-F004 to REQ-007-PRS-F007). REQ-001's draft rules are
tested through the sales drafts; these tests show the payment's bodies, its bank account,
its rules on references and amounts, its duplicate match by the bank's reference, its
warnings, and that the limit of drafts per hour counts payment entries on their own
(REQ-001-PRS-F019)."""

from typing import Any

import pytest

from tests.fakes.erpnext import (
    AGENT,
    COMPANY,
    FakeErpnext,
    account,
    bank_account,
    customer,
    payment_entry,
    purchase_invoice,
    sales_invoice,
    supplier,
)
from tests.fakes.settings import DRAFTS_PER_HOUR
from tests.integration.clock import TODAY
from tests.integration.mcp import Result, Session

PATH = "/api/resource/Payment Entry"
MAIN = "Main - Example Bank"
BANK = "1200 - Bank - EX"
INVOICE = "ACC-SINV-2026-00001"  # submitted, 119 outstanding
BILL = "ACC-PINV-2026-00001"  # submitted, the supplier's
DRAFT = "ACC-PAY-2026-00010"
MODIFIED = "2026-10-28 11:00:00.000000"
PAID = [{"reference_name": INVOICE, "allocated_amount": 119}]


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    erpnext.today = TODAY
    erpnext.add("Customer", customer("CUST-0001"))
    erpnext.add("Customer", customer("CUST-0002"))
    erpnext.add("Supplier", supplier("SUPP-0001"))
    erpnext.add("Bank Account", bank_account(MAIN))
    erpnext.add(
        "Bank Account", bank_account("Savings - Example Bank", account="1210 - Savings - EX")
    )
    erpnext.add("Bank Account", bank_account("Old - Example Bank", disabled=1))
    erpnext.add("Bank Account", bank_account("Main - Other Bank", company="Other AG"))
    erpnext.add(
        "Bank Account",
        bank_account(
            "Customer - Their Bank", is_company_account=0, party_type="Customer", party="CUST-0001"
        ),
    )
    erpnext.add("Sales Invoice", sales_invoice(INVOICE))
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00002", outstanding_amount=50.0))
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00003", customer="CUST-0002"))
    erpnext.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00004", docstatus=0, status="Draft"),
    )
    erpnext.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00005", docstatus=2, status="Cancelled"),
    )
    erpnext.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00006", outstanding_amount=0.0, status="Paid"),
    )
    erpnext.add(
        "Sales Invoice",
        sales_invoice("ACC-SINV-2026-00007", is_return=1, outstanding_amount=-119.0),
    )
    erpnext.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00008", company="Other AG"))
    erpnext.add("Purchase Invoice", purchase_invoice(BILL))
    erpnext.add("Payment Entry", payment_entry("ACC-PAY-2026-00001"))  # reference TX-4711
    erpnext.add(
        "Payment Entry",
        payment_entry(
            "ACC-PAY-2026-00002", reference_no="TX-4712", docstatus=2, status="Cancelled"
        ),
    )
    erpnext.add(
        "Payment Entry",
        payment_entry(
            DRAFT,
            reference_no="TX-4800",
            reference_date="2026-10-27",
            posting_date="2026-10-27",
            paid_amount=80.0,
            received_amount=80.0,
            unallocated_amount=0.0,
            docstatus=0,
            status="Draft",
            owner=AGENT,
            modified=MODIFIED,
            references=[
                {
                    "doctype": "Payment Entry Reference",
                    "reference_doctype": "Sales Invoice",
                    "reference_name": INVOICE,
                    "allocated_amount": 80.0,
                    "outstanding_amount": 119.0,
                }
            ],
        ),
    )
    return erpnext


def create(mcp: Session, **arguments: Any) -> Result:
    return mcp.call(
        "create_draft_payment_entry",
        {
            "party_type": "Customer",
            "party": "CUST-0001",
            "bank_account": MAIN,
            "paid_amount": 119,
            "reference_no": "TX-5000",
            **arguments,
        },
    )


def update(mcp: Session, name: str = DRAFT, modified: str = MODIFIED, **arguments: Any) -> Result:
    return mcp.call("update_draft_payment_entry", {"name": name, "modified": modified, **arguments})


# create_draft_payment_entry (REQ-007-PRS-F004)


def test_a_receipt_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    result = create(
        mcp,
        posting_date="2026-11-02",
        reference_date="2026-11-01",
        references=PAID,
    )
    assert not result.error, result.text
    [post] = erp.writes(PATH)
    assert (post.method, post.path) == ("POST", PATH)
    assert post.body == {
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": "CUST-0001",
        "bank_account": MAIN,
        "paid_to": BANK,
        "paid_amount": 119,
        "received_amount": 119,
        "reference_no": "TX-5000",
        "reference_date": "2026-11-01",
        "posting_date": "2026-11-02",
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": INVOICE,
                "allocated_amount": 119,
            }
        ],
        "company": COMPANY,
        "docstatus": 0,
    }


def test_a_payment_to_a_supplier_sends_pay_from_the_bank(mcp: Session, erp: FakeErpnext) -> None:
    result = create(
        mcp,
        party_type="Supplier",
        party="SUPP-0001",
        paid_amount=47.6,
        references=[{"reference_name": BILL, "allocated_amount": 47.6}],
    )
    assert not result.error, result.text
    [post] = erp.writes(PATH)
    assert post.body["payment_type"] == "Pay"
    assert post.body["paid_from"] == BANK
    assert "paid_to" not in post.body
    assert post.body["references"] == [
        {"reference_doctype": "Purchase Invoice", "reference_name": BILL, "allocated_amount": 47.6}
    ]


def test_a_create_without_dates_sends_today_for_both(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp)
    assert not result.error, result.text
    [post] = erp.writes(PATH)
    assert post.body == {
        "payment_type": "Receive",
        "party_type": "Customer",
        "party": "CUST-0001",
        "bank_account": MAIN,
        "paid_to": BANK,
        "paid_amount": 119,
        "received_amount": 119,
        "reference_no": "TX-5000",
        "reference_date": TODAY,
        "posting_date": TODAY,
        "company": COMPANY,
        "docstatus": 0,
    }


def test_the_reference_date_defaults_to_the_posting_date(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp, posting_date="2026-10-20")
    [post] = erp.writes(PATH)
    assert post.body["reference_date"] == "2026-10-20"


def test_a_create_returns_the_draft(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, paid_amount=119, references=PAID).data
    name = result["name"]
    assert name.startswith("ACC-PAY-")
    assert result == {
        "name": name,
        "modified": erp.docs["Payment Entry"][name]["modified"],
        "status": "Draft",
        "docstatus": 0,
        "company": COMPANY,
        "payment_type": "Receive",
        "posting_date": TODAY,
        "party_type": "Customer",
        "party": "CUST-0001",
        "bank_account": MAIN,
        "paid_from": "1400 - Debtors - EX",
        "paid_to": BANK,
        "paid_amount": 119,
        "received_amount": 119,
        "paid_from_account_currency": "EUR",
        "paid_to_account_currency": "EUR",
        "reference_date": TODAY,
        "total_allocated_amount": 119,
        "unallocated_amount": 0,
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": INVOICE,
                "allocated_amount": 119,
                "outstanding_amount": 119,
                "outside_text": {},
            }
        ],
        "url": f"https://erp.example.com/desk/payment-entry/{name}",
        "warnings": [],
        "truncated": [],
        "outside_text": {"reference_no": "TX-5000"},
    }


def test_the_create_says_how_to_retry(mcp: Session) -> None:
    tools = {t["name"]: t for t in mcp.tools()}
    description = tools["create_draft_payment_entry"]["description"]
    assert "`list_payment_entries` with `state` draft" in description


@pytest.mark.parametrize(
    "bank",
    [
        "Main - Other Bank",  # another company's
        "Customer - Their Bank",  # a party's
        "Old - Example Bank",  # disabled
        "Nowhere - No Bank",
    ],
)
def test_only_an_enabled_bank_account_of_the_company_is_taken(
    mcp: Session, erp: FakeErpnext, bank: str
) -> None:
    result = create(mcp, bank_account=bank)
    assert result.error
    assert result.text.startswith("bank_account: ")
    assert bank in result.text
    assert erp.writes() == []


def test_the_bank_account_is_read_by_its_name(mcp: Session, erp: FakeErpnext) -> None:
    create(mcp)
    read = next(r for r in erp.received if r.path == "/api/method/frappe.client.get")
    assert read.params == {"doctype": "Bank Account", "name": MAIN}


@pytest.mark.parametrize(
    ("arguments", "says"),
    [
        ({"paid_amount": 0}, "paid_amount: "),
        ({"paid_amount": -5}, "paid_amount: "),
        ({"paid_amount": 1.005}, "paid_amount: "),
        ({"paid_amount": 1_000_000_000.01}, "paid_amount: "),
        ({"party_type": "Employee", "party": "E-1"}, "party_type: "),
        ({"reference_no": ""}, "reference_no: "),
        ({"reference_no": " TX-1"}, "reference_no: "),
        ({"references": [{"reference_name": INVOICE, "allocated_amount": 0}]}, "references.0."),
        ({"references": [{"reference_name": INVOICE, "allocated_amount": 1.005}]}, "references.0."),
        ({"references": [{"reference_name": INVOICE}]}, "references.0.allocated_amount: "),
        (
            {"references": [{"reference_name": INVOICE, "allocated_amount": 1}] * 21},
            "references: List should have at most 20 items",
        ),
        (
            {"references": [{**PAID[0], "reference_doctype": "Journal Entry"}]},
            "references.0.reference_doctype: Extra inputs are not permitted",
        ),
        ({"payment_type": "Internal Transfer"}, "payment_type: Extra inputs are not permitted"),
        ({"paid_to": "1000 - Cash - EX"}, "paid_to: Extra inputs are not permitted"),
    ],
)
def test_inputs_outside_the_schema_are_refused(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], says: str
) -> None:
    result = create(mcp, **arguments)
    assert result.error
    assert says in result.text
    assert erp.received == []


def test_amounts_take_cents(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, paid_amount=10.05, references=[{**PAID[0], "allocated_amount": 3.35}])
    assert not result.error, result.text
    assert (result.data["paid_amount"], result.data["unallocated_amount"]) == (10.05, 6.7)


# The rules before ERPNext (REQ-007-PRS-F005)


@pytest.mark.parametrize(
    "invoice",
    [
        "ACC-SINV-2026-00003",  # another customer's
        "ACC-SINV-2026-00004",  # a draft
        "ACC-SINV-2026-00005",  # cancelled
        "ACC-SINV-2026-00006",  # paid
        "ACC-SINV-2026-00007",  # a return
        "ACC-SINV-2026-00008",  # another company's
        "ACC-SINV-2026-09999",
    ],
)
def test_only_the_partys_open_invoices_take_a_payment(
    mcp: Session, erp: FakeErpnext, invoice: str
) -> None:
    result = create(mcp, references=[{"reference_name": invoice, "allocated_amount": 10}])
    assert result.error
    assert result.text.startswith("references: ")
    assert invoice in result.text
    assert erp.writes() == []


def test_the_invoices_are_checked_in_one_catalogued_call(mcp: Session, erp: FakeErpnext) -> None:
    second = {"reference_name": "ACC-SINV-2026-00002", "allocated_amount": 50}
    result = create(mcp, paid_amount=169, references=[*PAID, second])
    assert not result.error, result.text
    [check] = erp.lists("/api/resource/Sales Invoice")
    assert check.param("fields") == [
        "name",
        "customer",
        "docstatus",
        "is_return",
        "outstanding_amount",
    ]
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["name", "in", [INVOICE, "ACC-SINV-2026-00002"]],
    ]


def test_a_purchase_invoice_on_hold_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Purchase Invoice", purchase_invoice("ACC-PINV-2026-00002", on_hold=1))
    held = [{"reference_name": "ACC-PINV-2026-00002", "allocated_amount": 10}]
    result = create(mcp, party_type="Supplier", party="SUPP-0001", references=held)
    assert result.error
    assert result.text.startswith("references: ")
    assert "ACC-PINV-2026-00002 is on hold" in result.text
    [check] = erp.lists("/api/resource/Purchase Invoice")
    assert check.param("fields") == [
        "name",
        "supplier",
        "docstatus",
        "is_return",
        "outstanding_amount",
        "on_hold",
    ]
    assert erp.writes() == []


def test_an_invoice_given_twice_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    twice = [{"reference_name": INVOICE, "allocated_amount": 10}] * 2
    result = create(mcp, paid_amount=20, references=twice)
    assert result.error
    assert result.text.startswith("references: ")
    assert INVOICE in result.text
    assert erp.writes() == []


def test_an_allocation_above_the_outstanding_amount_is_refused(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = create(
        mcp, references=[{"reference_name": "ACC-SINV-2026-00002", "allocated_amount": 50.01}]
    )
    assert result.error
    assert result.text.startswith("references: ")
    assert "ACC-SINV-2026-00002" in result.text
    assert "50" in result.text
    assert erp.writes() == []


def test_a_residual_below_one_takes_a_payment(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Sales Invoice", sales_invoice("ACC-SINV-2026-00009", outstanding_amount=0.5))
    residual = [{"reference_name": "ACC-SINV-2026-00009", "allocated_amount": 0.5}]
    result = create(mcp, paid_amount=0.5, references=residual)
    assert not result.error, result.text
    [post] = erp.writes(PATH)
    assert post.body["references"] == [
        {
            "reference_doctype": "Sales Invoice",
            "reference_name": "ACC-SINV-2026-00009",
            "allocated_amount": 0.5,
        }
    ]


def test_allocations_above_the_paid_amount_are_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, paid_amount=100, references=PAID)
    assert result.error
    assert result.text.startswith("references: ")
    assert "119" in result.text
    assert "100" in result.text
    assert erp.writes() == []


def test_a_payment_without_references_checks_no_invoice(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp)
    assert not result.error, result.text
    assert erp.lists("/api/resource/Sales Invoice") == []


# The duplicate match (REQ-007-PRS-F006)


def test_a_recorded_bank_reference_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, reference_no="TX-4711")
    assert result.error
    assert result.text.startswith("allow_duplicate: ")
    assert "ACC-PAY-2026-00001" in result.text
    assert erp.writes() == []
    [check] = erp.lists(PATH)
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["party_type", "=", "Customer"],
        ["party", "=", "CUST-0001"],
        ["reference_no", "=", "TX-4711"],
    ]


def test_a_drafts_bank_reference_is_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, reference_no="TX-4800")
    assert result.error
    assert DRAFT in result.text


@pytest.mark.parametrize(
    "arguments",
    [
        {"reference_no": "TX-4712"},  # cancelled
        {"reference_no": "TX-4711", "party": "CUST-0002"},  # another party's
    ],
)
def test_a_reference_not_recorded_for_the_party_goes_through(
    mcp: Session, arguments: dict[str, Any]
) -> None:
    result = create(mcp, **arguments)
    assert not result.error, result.text
    assert result.data["warnings"] == []


def test_allow_duplicate_warns(mcp: Session, erp: FakeErpnext) -> None:
    result = create(mcp, reference_no="TX-4711", allow_duplicate=True).data
    [warning] = result["warnings"]
    assert "ACC-PAY-2026-00001" in warning
    assert len(erp.comments) == 1


# Warnings (REQ-007-PRS-F007)


def test_a_part_not_allocated_warns(mcp: Session, erp: FakeErpnext) -> None:
    references = [{"reference_name": INVOICE, "allocated_amount": 20}]
    result = create(mcp, paid_amount=30, references=references).data
    assert result["unallocated_amount"] == 10
    [warning] = result["warnings"]
    assert "10" in warning
    assert "advance" in warning
    [comment] = erp.comments
    assert comment["reference_doctype"] == "Payment Entry"


def test_a_payment_without_references_doesnt_warn(mcp: Session) -> None:
    result = create(mcp, paid_amount=30).data
    assert result["unallocated_amount"] == 30
    assert result["warnings"] == []


def test_two_currencies_warn(mcp: Session, erp: FakeErpnext) -> None:
    erp.add("Account", account(BANK, account_currency="USD"))
    result = create(mcp).data
    [warning] = result["warnings"]
    assert "USD" in warning
    assert "EUR" in warning
    assert "received_amount" in warning
    assert "exchange rates" in warning
    assert "sent" not in warning


# update_draft_payment_entry


def test_an_update_sends_exactly_the_catalogued_body(mcp: Session, erp: FakeErpnext) -> None:
    result = update(
        mcp,
        bank_account="Savings - Example Bank",
        paid_amount=100,
        reference_no="TX-4801",
        reference_date="2026-10-26",
        posting_date="2026-10-28",
        references=[{"reference_name": INVOICE, "allocated_amount": 100}],
    )
    assert not result.error, result.text
    [put] = erp.writes(PATH)
    assert (put.method, put.path) == ("PUT", f"{PATH}/{DRAFT}")
    assert put.body == {
        "bank_account": "Savings - Example Bank",
        "paid_to": "1210 - Savings - EX",
        "paid_to_account_currency": None,
        "paid_to_account_type": None,
        "paid_amount": 100,
        "received_amount": 100,
        "reference_no": "TX-4801",
        "reference_date": "2026-10-26",
        "posting_date": "2026-10-28",
        "references": [
            {
                "reference_doctype": "Sales Invoice",
                "reference_name": INVOICE,
                "allocated_amount": 100,
            }
        ],
        "paid_from": None,
        "paid_from_account_currency": None,
        "paid_from_account_type": None,
        "modified": MODIFIED,
    }


def test_an_update_of_a_payment_to_a_supplier_sends_its_bank_as_paid_from(
    mcp: Session, erp: FakeErpnext
) -> None:
    erp.docs["Payment Entry"][DRAFT].update(
        payment_type="Pay", party_type="Supplier", party="SUPP-0001", references=[]
    )
    update(mcp, bank_account="Savings - Example Bank")
    [put] = erp.writes(PATH)
    assert put.body == {
        "bank_account": "Savings - Example Bank",
        "paid_from": "1210 - Savings - EX",
        "paid_from_account_currency": None,
        "paid_from_account_type": None,
        "modified": MODIFIED,
    }


def test_an_empty_list_removes_the_references(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, references=[])
    assert not result.error, result.text
    [put] = erp.writes(PATH)
    assert put.body == {
        "references": [],
        "paid_from": None,
        "paid_from_account_currency": None,
        "paid_from_account_type": None,
        "modified": MODIFIED,
    }
    assert result.data["references"] == []
    assert result.data["paid_from"] == "1400 - Debtors - EX"


def test_new_references_let_erpnext_set_the_party_account_again(
    mcp: Session, erp: FakeErpnext
) -> None:
    # A company booking advances apart gave the draft its advance account (REQ-007-PRS-F004)
    erp.docs["Payment Entry"][DRAFT].update(
        payment_type="Pay",
        party_type="Supplier",
        party="SUPP-0001",
        paid_to="1610 - Advances Paid - EX",
        paid_from=BANK,
        references=[],
    )
    references = [{"reference_name": BILL, "allocated_amount": 80}]
    result = update(mcp, references=references)
    assert not result.error, result.text
    [put] = erp.writes(PATH)
    assert put.body == {
        "references": [
            {
                "reference_doctype": "Purchase Invoice",
                "reference_name": BILL,
                "allocated_amount": 80,
            }
        ],
        "paid_to": None,
        "paid_to_account_currency": None,
        "paid_to_account_type": None,
        "modified": MODIFIED,
    }
    assert result.data["paid_to"] == "1600 - Creditors - EX"
    assert erp.lists("/api/resource/Sales Invoice") == []


def test_an_update_checks_the_references_for_the_drafts_party(
    mcp: Session, erp: FakeErpnext
) -> None:
    references = [{"reference_name": "ACC-SINV-2026-00003", "allocated_amount": 10}]
    result = update(mcp, references=references)
    assert result.error
    assert result.text.startswith("references: ")
    assert erp.writes() == []


def test_an_update_lowering_the_amount_below_the_allocations_is_refused(
    mcp: Session, erp: FakeErpnext
) -> None:
    result = update(mcp, paid_amount=70)
    assert result.error
    assert result.text.startswith("paid_amount: ")
    assert "80" in result.text
    assert "70" in result.text
    assert erp.writes() == []


def test_references_above_the_drafts_amount_are_refused(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, references=PAID)  # 119 against the draft's 80
    assert result.error
    assert result.text.startswith("references: ")
    assert erp.writes() == []


@pytest.mark.parametrize(
    ("arguments", "named"),
    [
        ({"party": "CUST-0002"}, "party"),
        ({"party_type": "Supplier"}, "party_type"),
        ({"allow_duplicate": True}, "allow_duplicate"),
        ({}, "at least one"),
    ],
)
def test_an_update_refuses_what_it_doesnt_take(
    mcp: Session, erp: FakeErpnext, arguments: dict[str, Any], named: str
) -> None:
    result = update(mcp, **arguments)
    assert result.error
    assert named in result.text
    assert erp.received == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"payment_type": "Internal Transfer", "party_type": None, "party": None},
        {"payment_type": "Pay"},  # a refund to a customer
        {"payment_type": "Receive", "party_type": "Supplier", "party": "SUPP-0001"},
        {"payment_type": "Receive", "party_type": "Employee", "party": "E-1"},
        {"payment_type": "Pay", "docstatus": 1},
        {"company": "Other AG"},
    ],
)
def test_what_enterich_doesnt_change_answers_as_unknown(
    mcp: Session, erp: FakeErpnext, overrides: dict[str, Any]
) -> None:
    other = payment_entry("ACC-PAY-2026-00012", **{"docstatus": 0, "owner": AGENT, **overrides})
    erp.add("Payment Entry", other)
    # Stale as well: the answer comes before the state and `modified` are checked.
    result = update(mcp, "ACC-PAY-2026-00012", "2026-01-01 00:00:00.000000", reference_no="X")
    unknown = update(mcp, "ACC-PAY-2026-09999", reference_no="X")
    assert result.error
    assert result.text.startswith("name: ")
    assert result.text.replace("00012", "") == unknown.text.replace("09999", "")
    assert erp.writes() == []


def test_a_draft_another_user_created_isnt_updated(mcp: Session, erp: FakeErpnext) -> None:
    erp.docs["Payment Entry"][DRAFT]["owner"] = "bookkeeper@example.com"
    result = update(mcp, reference_no="TX-4801")
    assert result.error
    assert "created by another user" in result.text
    assert erp.writes() == []


def test_a_stale_update_changes_nothing(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, modified="2026-10-28 10:00:00.000000", reference_no="TX-4801")
    assert result.error
    assert "changed" in result.text
    assert erp.writes() == []


def test_an_update_to_a_recorded_bank_reference_warns(mcp: Session, erp: FakeErpnext) -> None:
    result = update(mcp, reference_no="TX-4711").data
    [warning] = result["warnings"]
    assert "ACC-PAY-2026-00001" in warning
    [check] = erp.lists(PATH)
    assert check.param("filters") == [
        ["company", "=", COMPANY],
        ["docstatus", "in", [0, 1]],
        ["party_type", "=", "Customer"],
        ["party", "=", "CUST-0001"],
        ["reference_no", "=", "TX-4711"],
        ["name", "!=", DRAFT],
    ]
    [comment] = erp.comments
    assert comment["reference_name"] == DRAFT


def test_the_drafts_own_reference_doesnt_warn(mcp: Session) -> None:
    result = update(mcp, reference_no="TX-4800").data
    assert result["warnings"] == []


def test_an_update_warns_of_a_part_not_allocated(mcp: Session) -> None:
    result = update(mcp, paid_amount=100).data  # 80 allocated
    [warning] = result["warnings"]
    assert "20" in warning


# Drafts per hour (REQ-001-PRS-F019)


def test_the_limit_counts_payment_entries_on_their_own(limited: Session, erp: FakeErpnext) -> None:
    for number in range(DRAFTS_PER_HOUR):
        name = f"ACC-SINV-2026-{30 + number:05d}"
        erp.add("Sales Invoice", sales_invoice(name, creation="2026-10-29 01:30:00.000000"))
    assert not create(limited).error
    for number in range(DRAFTS_PER_HOUR - 1):
        name = f"ACC-PAY-2026-{30 + number:05d}"
        doc = payment_entry(name, owner=AGENT, creation="2026-10-29 01:30:00.000000")
        erp.add("Payment Entry", doc)
    result = create(limited, reference_no="TX-5001")
    assert result.error
    assert result.text.startswith(
        f"The agent user created {DRAFTS_PER_HOUR} payment entries in the last hour, "
    )
