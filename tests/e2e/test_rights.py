"""The rights (REQ-002-PRS-NF013): with only the rights its row of a Rights section lists,
each operation works; and each listed right is taken from the agent user's role in turn,
and the operations of its row that need it are refused. The role keeps what the other
rows list, and the user what ERPNext gives every desk user through the roles All and Desk
User. Where a right that stays keeps part of the access, the operation answers with less
instead (UNREFUSED). The seed's RIGHTS is the role, row by row.

Each removal is undone before the next; a run that stopped in between is undone by the
next seed. The drafts here use quantities and amounts from 41 up, which no other test
uses."""

import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import pytest

from tests.e2e.seed import (
    DEBTORS,
    RIGHTS,
    ROLE,
    Rights,
    Seed,
    granted,
    permissions,
    report_role,
)
from tests.e2e.site import Site
from tests.integration.mcp import Result, Session

CREDITORS = "2110 - Creditors - EX"
COST_CENTER = "Main - EX"


@dataclass(frozen=True)
class Removal:
    """One right of a row taken away: a DocType's permission type, or with `doctype`
    None the role on the report `right`."""

    row: Rights
    doctype: str | None
    right: str

    def __str__(self) -> str:
        what = f"{self.doctype} {self.right}" if self.doctype else f"the {self.right} report"
        return f"{self.row.operations[0]} without {what}"


REMOVALS = [
    *(
        Removal(row, doctype, right)
        for row in RIGHTS
        for doctype, rights in row.doctypes.items()
        for right in rights
    ),
    *(Removal(row, None, report) for row in RIGHTS for report in row.reports),
]


def works(answer: Result) -> None:
    assert not answer.error, answer.text


def without_addresses(answer: Result) -> None:
    """All's rule lets a user read only the addresses it made."""
    assert answer.data["addresses"] == []


def search_fields_only(field: str) -> Callable[[Result], None]:
    """With select alone ERPNext answers with the DocType's search fields only, so the
    records arrive without `field`."""

    def check(answer: Result) -> None:
        records = answer.data["records"]
        assert records
        assert [r[field] for r in records] == [None] * len(records)

    return check


# The operations a removed right doesn't refuse, and what they answer instead:
# (operation, DocType, right) -> a check of the answer
UNREFUSED: dict[tuple[str, str | None, str], Callable[[Result], None]] = {
    # Desk User's select on Item, and the sales drafts' select on Customer
    ("list_items", "Item", "read"): search_fields_only("item_code"),
    ("list_customers", "Customer", "read"): search_fields_only("customer_type"),
    ("list_customers", "Address", "read"): works,
    ("get_customer", "Address", "read"): without_addresses,
    ("list_suppliers", "Address", "read"): works,
    ("get_supplier", "Address", "read"): without_addresses,
    # Creating needs no write, and updating no create
    ("create_draft_sales_invoice", "Sales Invoice", "write"): works,
    ("update_draft_sales_invoice", "Sales Invoice", "create"): works,
    ("create_draft_purchase_invoice", "Purchase Invoice", "write"): works,
    ("update_draft_purchase_invoice", "Purchase Invoice", "create"): works,
    ("create_draft_journal_entry", "Journal Entry", "write"): works,
    ("update_draft_journal_entry", "Journal Entry", "create"): works,
}

# ERPNext's permission refusal, or Enterich's answer for a name it may not read
# (REQ-001-PRS-F009)
REFUSED = re.compile(
    r"^ERPNext refused the request \(403 PermissionError\)"
    r"|doesn't exist, or the agent user isn't permitted to read it\.$"
)


def sales(seeded: Seed) -> dict[str, Any]:
    """A draft that reaches every right of its row: items with account and unit, taxes."""
    return {
        "items": [
            {
                "item_code": seeded.item,
                "qty": 41,
                "rate": 1,
                "uom": "Nos",
                "income_account": "4110 - Sales - EX",
                "cost_center": COST_CENTER,
            }
        ],
        "taxes_and_charges": seeded.sales_template,
    }


def purchase(seeded: Seed) -> dict[str, Any]:
    """Likewise: items with account and unit, taxes."""
    return {
        "items": [
            {
                "item_code": seeded.item,
                "qty": 42,
                "rate": 1,
                "uom": "Nos",
                "expense_account": "5111 - Cost of Goods Sold - EX",
                "cost_center": COST_CENTER,
            }
        ],
        "taxes_and_charges": seeded.purchase_template,
    }


def journal(seeded: Seed) -> dict[str, Any]:
    """Rows with parties, invoice references and cost centres, which need no right."""
    return {
        "accounts": [
            {
                "account": DEBTORS,
                "credit": "43",
                "party_type": "Customer",
                "party": seeded.customer,
                "reference_type": "Sales Invoice",
                "reference_name": seeded.sales_invoice,
                "cost_center": COST_CENTER,
            },
            {
                "account": CREDITORS,
                "debit": "43",
                "party_type": "Supplier",
                "party": seeded.supplier,
                "reference_type": "Purchase Invoice",
                "reference_name": seeded.purchase_invoice,
                "cost_center": COST_CENTER,
            },
        ]
    }


def creates(seeded: Seed) -> dict[str, dict[str, Any]]:
    return {
        "create_draft_sales_invoice": {"customer": seeded.customer, **sales(seeded)},
        "create_draft_purchase_invoice": {"supplier": seeded.supplier, **purchase(seeded)},
        "create_draft_journal_entry": journal(seeded),
    }


def arguments(
    seeded: Seed, operation: str, removal: Removal | None, draft: dict[str, Any] | None
) -> dict[str, Any]:
    """The operation's input: one that reaches every right of its row, the removed one
    included."""
    year = {"from_date": f"{seeded.posted.year}-01-01", "to_date": f"{seeded.posted.year}-12-31"}
    if operation in (made := creates(seeded)):
        return {**made[operation], "allow_duplicate": True}
    if draft is not None:
        changes = {
            "update_draft_sales_invoice": sales(seeded),
            "update_draft_purchase_invoice": purchase(seeded),
            "update_draft_journal_entry": journal(seeded),
        }[operation]
        return {"name": draft["name"], "modified": draft["modified"], **changes}
    party = (
        ("Supplier", seeded.supplier)
        if removal and removal.doctype == "Supplier"
        else ("Customer", seeded.customer)
    )
    return {
        "list_items": {"search": "SKU"},
        "get_item": {"item_code": seeded.item},
        "list_customers": {"search": "Example"},
        "get_customer": {"name": seeded.customer},
        "list_sales_invoices": {"customer": seeded.customer},
        "get_sales_invoice": {"name": seeded.sales_invoice},
        "list_sales_tax_templates": {},
        "report_accounts_receivable": {"customer": seeded.customer},
        "list_suppliers": {"search": "Example"},
        "get_supplier": {"name": seeded.supplier},
        "list_purchase_invoices": {"supplier": seeded.supplier},
        "get_purchase_invoice": {"name": seeded.purchase_invoice},
        "list_purchase_tax_templates": {},
        "report_accounts_payable": {"supplier": seeded.supplier},
        "list_accounts": {"search": "Debtors"},
        "list_cost_centers": {},
        "list_journal_entries": {},
        "get_journal_entry": {"name": seeded.journal_entry},
        "report_general_ledger": {
            **year,
            "account": DEBTORS,
            "party_type": party[0],
            "party": party[1],
        },
        "report_trial_balance": {**year, "limit": 100},
        "list_bank_accounts": {},
        "list_bank_transactions": {"bank_account": seeded.bank_account},
        "get_bank_transaction": {"name": seeded.bank_transaction},
        "list_payment_entries": {},
        "get_payment_entry": {"name": seeded.payment_entry},
    }[operation]


def updated(mcp: Session, seeded: Seed, row: Rights) -> dict[str, dict[str, Any]]:
    """Drafts for the row's update operations, made with the role as it is."""
    drafts: dict[str, dict[str, Any]] = {}
    for op in row.operations:
        if op.startswith("update_draft_"):
            create = op.replace("update_", "create_")
            made = mcp.call(create, arguments(seeded, create, None, None))
            assert not made.error, made.text
            drafts[op] = made.data
    return drafts


@contextmanager
def withdrawn(site: Site, removal: Removal) -> Generator[None]:
    """The role without the removed right; with every right of RIGHTS again afterwards."""
    try:
        if removal.doctype is None:
            [custom] = site.get_list("Custom Role", {"report": removal.right})
            roles = site.call("frappe.client.get", doctype="Custom Role", name=custom["name"])
            site.update(
                "Custom Role",
                custom["name"],
                {"roles": [r for r in roles["roles"] if r["role"] != ROLE]},
            )
        else:
            permissions(site, granted((removal.doctype, removal.right)))
        yield
    finally:
        if removal.doctype is None:
            report_role(site, removal.right)
        else:
            permissions(site)


@pytest.fixture(scope="module")
def restored(site: Site) -> Generator[None]:
    """Every right of RIGHTS again after the module."""
    yield
    permissions(site)


def test_every_unrefused_operation_is_one_of_a_removal() -> None:
    """UNREFUSED names no operation, DocType and right that no row lists together."""
    listed = {(op, r.doctype, r.right) for r in REMOVALS for op in r.row.operations}
    assert UNREFUSED.keys() <= listed


@pytest.mark.usefixtures("restored")
@pytest.mark.parametrize("row", RIGHTS, ids=lambda row: row.operations[0])
def test_the_rights_of_a_row_suffice_for_its_operations(
    mcp: Session, seeded: Seed, site: Site, row: Rights
) -> None:
    # The role keeps the row's rights alone until the next test sets its own: a row's
    # rules differ little from the next one's, and `restored` gives every right back
    permissions(site, granted(rows=(row,)))
    drafts = updated(mcp, seeded, row)
    for op in row.operations:
        answer = mcp.call(op, arguments(seeded, op, None, drafts.get(op)))
        assert not answer.error, (op, answer.text)


@pytest.mark.usefixtures("restored")
@pytest.mark.parametrize("removal", REMOVALS, ids=str)
def test_a_removed_right_refuses_the_operations_that_need_it(
    mcp: Session, seeded: Seed, site: Site, removal: Removal
) -> None:
    permissions(site)
    drafts = updated(mcp, seeded, removal.row)
    with withdrawn(site, removal):
        answers = {
            op: mcp.call(op, arguments(seeded, op, removal, drafts.get(op)))
            for op in removal.row.operations
        }
    for op, answer in answers.items():
        if check := UNREFUSED.get((op, removal.doctype, removal.right)):
            check(answer)
        else:
            assert answer.error, (op, answer.text)
            assert REFUSED.search(answer.text), (op, answer.text)
