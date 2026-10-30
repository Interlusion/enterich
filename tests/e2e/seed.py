"""The seeded company and the agent user, made through the REST API as Administrator.

Seeding is idempotent: a site kept running by scripts/erpnext-site.sh is seeded once,
and later runs find what is there. Only the agent's API secret is new for each run.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from enterich.shapes import today
from tests.e2e.site import Site

COMPANY = "Example GmbH"
ABBR = "EX"
TIMEZONE = "Europe/Berlin"  # the site's and Enterich's, so both have the same today
ROLE = "Enterich Agent"
AGENT = "enterich-agent@example.com"


def site_today() -> date:
    """Today on the site, not on the machine running the tests."""
    return today(ZoneInfo(TIMEZONE))


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
    customer_address: str
    supplier_address: str
    sales_template: str
    purchase_template: str
    bank_ledger: str
    bank_account: str
    # Submitted, for the reads and reports; all posted on `posted`.
    sales_invoice: str
    purchase_invoice: str
    payment_entry: str
    journal_entry: str
    bank_transaction: str
    posted: date
    sales_due: date


def seed(site: Site) -> Seed:
    """Every step finds what a run before it made, so a run that failed halfway is
    completed by the next one."""
    company(site)
    fiscal_year(site, site_today().year)
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
    customer_address = address(site, "Customer", customer)
    supplier_address = address(site, "Supplier", supplier)
    sales_template = tax_template(site, "Sales Taxes and Charges Template", SALES_VAT)
    purchase_template = tax_template(site, "Purchase Taxes and Charges Template", INPUT_VAT)
    bank_ledger, bank_account = bank(site)
    vouchers = Vouchers(site, item, bank_ledger, bank_account)
    sales_invoice = vouchers.sales_invoice(customer, sales_template)
    purchase_invoice = vouchers.purchase_invoice(supplier, purchase_template)
    payment_entry = vouchers.payment_entry(customer, sales_invoice)
    journal_entry = vouchers.journal_entry()
    bank_transaction = vouchers.bank_transaction()
    keys = site.call("frappe.core.doctype.user.user.generate_keys", user=AGENT)
    return Seed(
        api_key=keys["api_key"],
        api_secret=keys["api_secret"],
        item=item,
        customer=customer,
        supplier=supplier,
        customer_address=customer_address,
        supplier_address=supplier_address,
        sales_template=sales_template,
        purchase_template=purchase_template,
        bank_ledger=bank_ledger,
        bank_account=bank_account,
        sales_invoice=sales_invoice,
        purchase_invoice=purchase_invoice,
        payment_entry=payment_entry,
        journal_entry=journal_entry,
        bank_transaction=bank_transaction,
        posted=vouchers.posted,
        sales_due=vouchers.sales_due,
    )


def company(site: Site) -> None:
    """The setup wizard: the company with its chart of accounts, taxes and a fiscal year."""
    if site.exists("Company", {"name": COMPANY}):
        return
    year = site_today().year
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


# The accounts the seed books on, from the setup wizard's chart
DEBTORS = f"1310 - Debtors - {ABBR}"
CAPITAL = f"3100 - Capital Stock - {ABBR}"
BANK_GROUP = f"1200 - Bank Accounts - {ABBR}"
SALES_VAT = ("VAT 19 %", f"2320 - Umsatzsteuer 19 % - {ABBR}")
INPUT_VAT = ("Input VAT 19 %", f"1520 - Abziehbare Vorsteuer 19 % - {ABBR}")
VAT_RATE = 19
SALES_TERMS = timedelta(days=30)
PURCHASE_TERMS = timedelta(days=14)
# A well-known example IBAN with a valid check sum; ERPNext checks it.
IBAN = "DE89370400440532013000"


def address(site: Site, party_type: str, party: str) -> str:
    return ensure(
        site,
        "Address",
        {"address_title": party},
        address_type="Billing",
        address_line1="Example Street 1",
        city="Example City",
        pincode="12345",
        country="Germany",
        links=[{"link_doctype": party_type, "link_name": party}],
    )


def tax_template(site: Site, doctype: str, vat: tuple[str, str]) -> str:
    """One with a rate: the setup wizard's German templates carry 0 % and leave the rate
    to item tax templates."""
    return ensure(site, doctype, {"title": vat[0], "company": COMPANY}, taxes=vat_rows(vat))


def vat_rows(vat: tuple[str, str]) -> list[dict[str, Any]]:
    """The tax rows of a template, and of the invoices made with it."""
    title, account = vat
    return [
        {
            "charge_type": "On Net Total",
            "account_head": account,
            "rate": VAT_RATE,
            "description": title,
        }
    ]


def bank(site: Site) -> tuple[str, str]:
    """The company's bank: its ledger account and its Bank Account."""
    ensure(site, "Bank", {"bank_name": "Example Bank"})
    ledger = ensure(
        site,
        "Account",
        {"account_name": "Example Bank", "company": COMPANY},
        account_number="1210",
        parent_account=BANK_GROUP,
        account_type="Bank",
    )
    account = ensure(
        site,
        "Bank Account",
        {"account_name": "Main", "company": COMPANY},
        bank="Example Bank",
        account=ledger,
        is_company_account=1,
        iban=IBAN,
    )
    return ledger, account


class Vouchers:
    """Submitted vouchers, each found by a reference only the seed uses. A kept site keeps
    those of its first run, so `posted` and `sales_due` are read from the sales invoice."""

    def __init__(self, site: Site, item: str, bank_ledger: str, bank_account: str) -> None:
        self.site = site
        self.item = item
        self.bank_ledger = bank_ledger
        self.bank_account = bank_account
        found = site.get_list("Sales Invoice", {"po_no": "SEED-SI-1"}, ["posting_date", "due_date"])
        if found:
            self.posted = date.fromisoformat(found[0]["posting_date"])
            self.sales_due = date.fromisoformat(found[0]["due_date"])
        else:
            self.posted = site_today()
            self.sales_due = self.posted + SALES_TERMS

    def submitted(self, doctype: str, identity: dict[str, str], **fields: Any) -> str:
        return ensure(self.site, doctype, identity, company=COMPANY, docstatus=1, **fields)

    def sales_invoice(self, customer: str, template: str) -> str:
        return self.submitted(
            "Sales Invoice",
            {"po_no": "SEED-SI-1"},
            customer=customer,
            posting_date=self.posted.isoformat(),
            set_posting_time=1,
            due_date=self.sales_due.isoformat(),
            items=[{"item_code": self.item, "qty": 2, "rate": 50}],
            taxes_and_charges=template,
            taxes=vat_rows(SALES_VAT),
        )

    def purchase_invoice(self, supplier: str, template: str) -> str:
        return self.submitted(
            "Purchase Invoice",
            {"bill_no": "SEED-BILL-1"},
            supplier=supplier,
            bill_date=self.posted.isoformat(),
            posting_date=self.posted.isoformat(),
            set_posting_time=1,
            due_date=(self.posted + PURCHASE_TERMS).isoformat(),
            items=[{"item_code": self.item, "qty": 1, "rate": 40}],
            taxes_and_charges=template,
            taxes=vat_rows(INPUT_VAT),
        )

    def payment_entry(self, customer: str, invoice: str) -> str:
        """Part of the sales invoice paid into the bank."""
        return self.submitted(
            "Payment Entry",
            {"reference_no": "SEED-PAY-1"},
            payment_type="Receive",
            posting_date=self.posted.isoformat(),
            reference_date=self.posted.isoformat(),
            mode_of_payment="Wire Transfer",
            party_type="Customer",
            party=customer,
            paid_from=DEBTORS,
            paid_to=self.bank_ledger,
            bank_account=self.bank_account,
            paid_amount=50,
            received_amount=50,
            references=[
                {
                    "reference_doctype": "Sales Invoice",
                    "reference_name": invoice,
                    "allocated_amount": 50,
                }
            ],
        )

    def journal_entry(self) -> str:
        """Capital paid into the bank."""
        return self.submitted(
            "Journal Entry",
            {"cheque_no": "SEED-JE-1"},
            voucher_type="Bank Entry",
            posting_date=self.posted.isoformat(),
            cheque_date=self.posted.isoformat(),
            user_remark="Capital paid in",
            accounts=[
                {"account": self.bank_ledger, "debit_in_account_currency": 1000},
                {
                    "account": CAPITAL,
                    "credit_in_account_currency": 1000,
                },
            ],
        )

    def bank_transaction(self) -> str:
        """A deposit from the statement, not yet reconciled."""
        return self.submitted(
            "Bank Transaction",
            {"reference_number": "SEED-BT-1"},
            date=self.posted.isoformat(),
            bank_account=self.bank_account,
            deposit=25,
            currency="EUR",
            description="Example Customer, invoice payment",
        )


def ensure(site: Site, doctype: str, identity: dict[str, str], **fields: Any) -> str:
    """The record matching `identity`, inserted with `fields` if missing; returns its name."""
    found = site.get_list(doctype, identity)
    if found:
        return found[0]["name"]
    return site.insert({"doctype": doctype, **identity, **fields})["name"]
