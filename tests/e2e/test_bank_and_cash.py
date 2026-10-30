"""Bank and cash against the seeded site: the company's bank accounts, bank transactions
and payment entries (REQ-007-PRS-F001 to REQ-007-PRS-F003)."""

from tests.e2e.seed import DEBTORS, IBAN, Seed
from tests.integration.mcp import Session


def test_list_bank_accounts(mcp: Session, seeded: Seed) -> None:
    records = mcp.call("list_bank_accounts", {}).data["records"]
    assert (seeded.bank_account, "Example Bank", seeded.bank_ledger, IBAN) in [
        (r["name"], r["bank"], r["account"], r["iban"]) for r in records
    ]


def test_an_unreconciled_bank_transaction(mcp: Session, seeded: Seed) -> None:
    day = seeded.posted.isoformat()
    records = mcp.call(
        "list_bank_transactions",
        {"bank_account": seeded.bank_account, "from_date": day, "to_date": day},
    ).data["records"]
    assert [(r["name"], r["deposit"], r["unallocated_amount"], r["status"]) for r in records] == [
        (seeded.bank_transaction, 25, 25, "Unreconciled")
    ]
    for state in ("reconciled", "pending"):
        others = mcp.call(
            "list_bank_transactions", {"bank_account": seeded.bank_account, "state": state}
        ).data["records"]
        assert seeded.bank_transaction not in [r["name"] for r in others], state


def test_get_bank_transaction(mcp: Session, seeded: Seed) -> None:
    transaction = mcp.call("get_bank_transaction", {"name": seeded.bank_transaction}).data
    assert (transaction["currency"], transaction["payment_entries"]) == ("EUR", [])
    assert transaction["outside_text"]["reference_number"] == "SEED-BT-1"


def test_list_payment_entries_with_every_filter(mcp: Session, seeded: Seed) -> None:
    day = seeded.posted.isoformat()
    records = mcp.call(
        "list_payment_entries",
        {
            "payment_type": "Receive",
            "party_type": "Customer",
            "party": seeded.customer,
            "state": "submitted",
            "from_date": day,
            "to_date": day,
        },
    ).data["records"]
    assert [(r["name"], r["paid_amount"], r["bank_account"]) for r in records] == [
        (seeded.payment_entry, 50, seeded.bank_account)
    ]


def test_get_payment_entry_with_its_references(mcp: Session, seeded: Seed) -> None:
    entry = mcp.call("get_payment_entry", {"name": seeded.payment_entry}).data
    assert (entry["paid_from"], entry["paid_to"]) == (DEBTORS, seeded.bank_ledger)
    assert [
        (r["reference_doctype"], r["reference_name"], r["allocated_amount"])
        for r in entry["references"]
    ] == [("Sales Invoice", seeded.sales_invoice, 50)]
    assert entry["outside_text"]["reference_no"] == "SEED-PAY-1"
