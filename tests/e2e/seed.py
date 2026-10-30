"""The seeded company and the agent user, made through the REST API as Administrator.

Seeding is idempotent: a site kept running by scripts/erpnext-site.sh is seeded once,
and later runs find what is there. Only the agent's API secret is new for each run.
"""

from dataclasses import dataclass
from datetime import date
from typing import Any

from tests.e2e.site import Site

COMPANY = "Example GmbH"
ABBR = "EX"
TIMEZONE = "Europe/Berlin"  # the site's and Enterich's, so both have the same today
ROLE = "Enterich Agent"
AGENT = "enterich-agent@example.com"


@dataclass(frozen=True)
class Rights:
    """One row of an area spec's Rights section."""

    operations: tuple[str, ...]
    doctypes: dict[str, tuple[str, ...]]
    reports: tuple[str, ...] = ()


# The area specs' Rights sections, row by row (REQ-002-PRS-NF013). "select" alone means
# select without read.
RIGHTS = (
    Rights(("list_items", "get_item"), {"Item": ("read",)}),
    Rights(("list_customers", "get_customer"), {"Customer": ("read",), "Address": ("read",)}),
    Rights(("list_sales_invoices", "get_sales_invoice"), {"Sales Invoice": ("read",)}),
    Rights(("list_sales_tax_templates",), {"Sales Taxes and Charges Template": ("read",)}),
    Rights(
        ("report_accounts_receivable",),
        {"Sales Invoice": ("read", "report"), "Journal Entry": ("read",)},
        ("Accounts Receivable",),
    ),
    Rights(
        ("create_draft_sales_invoice", "update_draft_sales_invoice"),
        {
            "Sales Invoice": ("read", "create", "write"),
            **dict.fromkeys(
                (
                    "Customer",
                    "Address",
                    "Item",
                    "Account",
                    "Cost Center",
                    "Sales Taxes and Charges Template",
                ),
                ("read",),
            ),
            **dict.fromkeys(
                ("Company", "Currency", "UOM", "Price List", "Payment Terms Template", "Project"),
                ("select",),
            ),
        },
    ),
    Rights(("list_suppliers", "get_supplier"), {"Supplier": ("read",), "Address": ("read",)}),
    Rights(("list_purchase_invoices", "get_purchase_invoice"), {"Purchase Invoice": ("read",)}),
    Rights(("list_purchase_tax_templates",), {"Purchase Taxes and Charges Template": ("read",)}),
    Rights(
        ("report_accounts_payable",),
        {"Purchase Invoice": ("read", "report"), "Journal Entry": ("read",)},
        ("Accounts Payable",),
    ),
    Rights(
        ("create_draft_purchase_invoice", "update_draft_purchase_invoice"),
        {
            "Purchase Invoice": ("read", "create", "write"),
            **dict.fromkeys(
                (
                    "Supplier",
                    "Address",
                    "Item",
                    "Account",
                    "Cost Center",
                    "Purchase Taxes and Charges Template",
                ),
                ("read",),
            ),
            **dict.fromkeys(
                ("Company", "Currency", "UOM", "Price List", "Payment Terms Template", "Project"),
                ("select",),
            ),
        },
    ),
    Rights(("list_accounts",), {"Account": ("read",)}),
    Rights(("list_cost_centers",), {"Cost Center": ("read",)}),
    Rights(("list_journal_entries", "get_journal_entry"), {"Journal Entry": ("read",)}),
    Rights(
        ("report_general_ledger",),
        # Customer or Supplier: the one of the `party` given.
        {
            "GL Entry": ("read", "report"),
            "Account": ("read",),
            "Customer": ("read",),
            "Supplier": ("read",),
        },
        ("General Ledger",),
    ),
    Rights(
        ("report_trial_balance",),
        {"GL Entry": ("read", "report"), "Account": ("read",), "Fiscal Year": ("read",)},
        ("Trial Balance",),
    ),
    Rights(
        ("create_draft_journal_entry", "update_draft_journal_entry"),
        {
            "Journal Entry": ("read", "create", "write"),
            "Account": ("read",),
            "Cost Center": ("read",),
            **dict.fromkeys(
                ("Company", "Customer", "Supplier", "Sales Invoice", "Purchase Invoice"),
                ("select",),
            ),
        },
    ),
    Rights(("list_bank_accounts",), {"Bank Account": ("read",)}),
    Rights(("list_bank_transactions", "get_bank_transaction"), {"Bank Transaction": ("read",)}),
    Rights(("list_payment_entries", "get_payment_entry"), {"Payment Entry": ("read",)}),
)


def granted() -> dict[str, set[str]]:
    """Every DocType's rights over all rows; read makes select needless."""
    union: dict[str, set[str]] = {}
    for row in RIGHTS:
        for doctype, rights in row.doctypes.items():
            union.setdefault(doctype, set()).update(rights)
    for rights in union.values():
        if "read" in rights:
            rights.discard("select")
    return union


@dataclass(frozen=True)
class Seed:
    api_key: str
    api_secret: str
    item: str
    customer: str
    supplier: str


def seed(site: Site) -> Seed:
    """Every step finds what a run before it made, so a run that failed halfway is
    completed by the next one."""
    company(site)
    fiscal_year(site, date.today().year)
    agent(site)
    item = ensure(
        site,
        "Item",
        {"item_code": "SKU-1"},
        item_name="Widget SKU-1",
        item_group="Products",
        stock_uom="Nos",
    )
    customer = ensure(
        site, "Customer", {"customer_name": "Example Customer"}, customer_type="Company"
    )
    supplier = ensure(
        site, "Supplier", {"supplier_name": "Example Supplier"}, supplier_type="Company"
    )
    keys = site.call("frappe.core.doctype.user.user.generate_keys", user=AGENT)
    return Seed(keys["api_key"], keys["api_secret"], item, customer, supplier)


def company(site: Site) -> None:
    """The setup wizard: the company with its chart of accounts, taxes and a fiscal year."""
    if site.exists("Company", {"name": COMPANY}):
        return
    year = date.today().year
    site.call(
        "frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
        args={
            "language": "English",
            "country": "Germany",
            "timezone": TIMEZONE,
            "currency": "EUR",
            "company_name": COMPANY,
            "company_abbr": ABBR,
            "chart_of_accounts": "Standard with Numbers",
            "fy_start_date": f"{year}-01-01",
            "fy_end_date": f"{year}-12-31",
            "enable_telemetry": 0,
        },
    )


def fiscal_year(site: Site, year: int) -> None:
    """This year's, for a site kept running into a new year."""
    ensure(
        site,
        "Fiscal Year",
        {"year": str(year)},
        year_start_date=f"{year}-01-01",
        year_end_date=f"{year}-12-31",
    )


def agent(site: Site) -> None:
    """The agent user with one role, whose rights are made to equal RIGHTS on each run: a
    kept site follows changes to RIGHTS, and a run that removed a right is undone."""
    ensure(site, "Role", {"role_name": ROLE}, desk_access=1)
    permissions(site)
    for report in sorted({r for row in RIGHTS for r in row.reports}):
        report_role(site, report)
    ensure(
        site,
        "User",
        {"email": AGENT},
        first_name="Enterich",
        last_name="Agent",
        user_type="System User",
        send_welcome_email=0,
        roles=[{"role": ROLE}],
    )


MANAGER = "frappe.core.page.permission_manager.permission_manager"
# The rights of a DocType permission rule the role is set for: those of RIGHTS, and
# none of the others, never submit, cancel, amend or delete.
PERMISSION_TYPES = (
    "read",
    "select",
    "report",
    "create",
    "write",
    "submit",
    "cancel",
    "amend",
    "delete",
    "print",
    "email",
    "export",
    "import",
    "share",
)


def permissions(site: Site) -> None:
    """The role's rules, set as the role permission manager does; one call when they match."""
    wanted = granted()
    held = {
        rule["parent"]: rule
        for rule in site.call(f"{MANAGER}.get_permissions", role=ROLE)
        if rule["permlevel"] == 0
    }
    for doctype in held.keys() - wanted.keys():
        site.call(f"{MANAGER}.remove", doctype=doctype, role=ROLE, permlevel=0)
    for doctype, rights in wanted.items():
        rule = held.get(doctype)
        if rule is None:
            site.call(f"{MANAGER}.add", parent=doctype, role=ROLE, permlevel=0)
            rule = {"read": 1}
        for ptype in PERMISSION_TYPES:
            value = int(ptype in rights)
            if int(rule.get(ptype) or 0) != value:
                site.call(
                    f"{MANAGER}.update",
                    doctype=doctype,
                    role=ROLE,
                    permlevel=0,
                    ptype=ptype,
                    value=value,
                )


def report_role(site: Site, report: str) -> None:
    """The role added to a report. A Custom Role's roles replace the report's own, so it
    carries those too, as the configuration guide tells deployers."""
    found = site.get_list("Custom Role", {"report": report})
    if found:
        custom = site.call("frappe.client.get", doctype="Custom Role", name=found[0]["name"])
        roles = [r["role"] for r in custom["roles"]]
        if ROLE not in roles:
            site.update(
                "Custom Role", custom["name"], {"roles": [*custom["roles"], {"role": ROLE}]}
            )
        return
    standard = site.call("frappe.client.get", doctype="Report", name=report)
    roles = [{"role": r["role"]} for r in standard["roles"]]
    site.insert({"doctype": "Custom Role", "report": report, "roles": [*roles, {"role": ROLE}]})


def ensure(site: Site, doctype: str, identity: dict[str, str], **fields: Any) -> str:
    """The record matching `identity`, inserted with `fields` if missing; returns its name."""
    found = site.get_list(doctype, identity)
    if found:
        return found[0]["name"]
    return site.insert({"doctype": doctype, **identity, **fields})["name"]
