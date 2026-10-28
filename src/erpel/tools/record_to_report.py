"""Record to report: accounts, cost centres, journal entries, the General Ledger and the
Trial Balance (REQ-006)."""

from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import model_validator

from erpel.erpnext import ErpnextError
from erpel.shapes import (
    Day,
    Flag,
    Inputs,
    Limit,
    Name,
    Offset,
    Search,
    cut_rows,
    cut_texts,
    decimal,
    form_url,
    in_order,
    like_pattern,
    page,
    rows_of,
    shape,
    split_outside,
)
from erpel.tools import Context, Operation, Refusal, get_named, report_rows

ACCOUNT_FIELDS = (
    "name",
    "account_number",
    "account_name",
    "root_type",
    "account_type",
    "parent_account",
    "is_group",
    "disabled",
)
COST_CENTER_FIELDS = (
    "name",
    "cost_center_number",
    "cost_center_name",
    "parent_cost_center",
    "is_group",
    "disabled",
)
JOURNAL_FIELDS = (
    "name",
    "voucher_type",
    "posting_date",
    "total_debit",
    "total_credit",
    "user_remark",
    "docstatus",
    "owner",
    "modified",
)
JOURNAL_DETAIL_FIELDS = ("cheque_no", "cheque_date")
JOURNAL_OUTSIDE = {"user_remark", "cheque_no"}
JOURNAL_ROW_FIELDS = (
    "account",
    "account_currency",
    "party_type",
    "party",
    "debit_in_account_currency",
    "credit_in_account_currency",
    "cost_center",
    "reference_type",
    "reference_name",
    "user_remark",
)
JOURNAL_ROW_OUTSIDE = {"user_remark"}
JOURNAL_STATES = {"draft": 0, "submitted": 1, "cancelled": 2}
LEDGER_FIELDS = (
    "posting_date",
    "account",
    "debit",
    "credit",
    "balance",
    "voucher_type",
    "voucher_no",
    "party_type",
    "party",
    "against",
    "remarks",
)
LEDGER_OUTSIDE = {"against", "remarks"}
MAX_LEDGER_DAYS = 366
BALANCE_VALUES = (
    "opening_debit",
    "opening_credit",
    "debit",
    "credit",
    "closing_debit",
    "closing_credit",
)
MAX_FISCAL_YEAR_ROWS = 1000  # one per company a year is assigned to

# ERPNext v16's voucher types (Journal Entry's voucher_type options)
type VoucherType = Literal[
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


class ListAccounts(Inputs):
    search: Search | None = None
    root_type: Literal["Asset", "Liability", "Equity", "Income", "Expense"] | None = None
    include_groups: Flag = False
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class ListCostCenters(Inputs):
    search: Search | None = None
    include_groups: Flag = False
    include_disabled: Flag = False
    limit: Limit = 20
    offset: Offset = 0


class ListJournalEntries(Inputs):
    state: Literal["draft", "submitted", "cancelled"] | None = None
    voucher_type: VoucherType | None = None
    from_date: Day | None = None
    to_date: Day | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _period(self) -> Self:
        in_order(self.from_date, self.to_date)
        return self


class GetJournalEntry(Inputs):
    name: Name


class ReportGeneralLedger(Inputs):
    from_date: Day
    to_date: Day
    account: Name | None = None
    party_type: Literal["Customer", "Supplier"] | None = None
    party: Name | None = None
    voucher_no: Name | None = None
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _rules(self) -> Self:
        in_order(self.from_date, self.to_date)
        if (self.to_date - self.from_date).days + 1 > MAX_LEDGER_DAYS:
            raise ValueError(
                f"from_date to to_date must span at most {MAX_LEDGER_DAYS} days, both included"
            )
        if self.party is not None and self.party_type is None:
            raise ValueError("party needs party_type")
        return self


class ReportTrialBalance(Inputs):
    from_date: Day
    to_date: Day
    show_zero_values: Flag = False
    limit: Limit = 20
    offset: Offset = 0

    @model_validator(mode="after")
    def _period(self) -> Self:
        in_order(self.from_date, self.to_date)
        return self


async def _tree(
    context: Context,
    doctype: str,
    fields: tuple[str, ...],
    searched: tuple[str, ...],
    filters: list[list[Any]],
    inputs: ListAccounts | ListCostCenters,
) -> dict[str, Any]:
    """A list of a company's accounts or cost centres: ledger ones unless groups are asked
    for, enabled ones unless disabled ones are."""
    filters = [["company", "=", context.settings.company], *filters]
    if not inputs.include_groups:
        filters.append(["is_group", "=", 0])
    if not inputs.include_disabled:
        filters.append(["disabled", "=", 0])
    or_filters: list[list[Any]] = []
    if inputs.search is not None:
        pattern = like_pattern(inputs.search)
        or_filters = [[f, "like", pattern] for f in searched]
    rows = await context.erpnext.get_list(
        doctype,
        fields=fields,
        filters=filters,
        or_filters=or_filters,
        order_by="name asc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, fields, flags={"is_group", "disabled"}) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def list_accounts(inputs: ListAccounts, context: Context) -> dict[str, Any]:
    filters = [] if inputs.root_type is None else [["root_type", "=", inputs.root_type]]
    searched = ("name", "account_name", "account_number")
    return await _tree(context, "Account", ACCOUNT_FIELDS, searched, filters, inputs)


async def list_cost_centers(inputs: ListCostCenters, context: Context) -> dict[str, Any]:
    searched = ("name", "cost_center_name", "cost_center_number")
    return await _tree(context, "Cost Center", COST_CENTER_FIELDS, searched, [], inputs)


async def list_journal_entries(inputs: ListJournalEntries, context: Context) -> dict[str, Any]:
    filters: list[list[Any]] = [["company", "=", context.settings.company]]
    if inputs.state is not None:
        filters.append(["docstatus", "=", JOURNAL_STATES[inputs.state]])
    if inputs.voucher_type is not None:
        filters.append(["voucher_type", "=", inputs.voucher_type])
    if inputs.from_date is not None:
        filters.append(["posting_date", ">=", inputs.from_date.isoformat()])
    if inputs.to_date is not None:
        filters.append(["posting_date", "<=", inputs.to_date.isoformat()])
    rows = await context.erpnext.get_list(
        "Journal Entry",
        fields=JOURNAL_FIELDS,
        filters=filters,
        order_by="posting_date desc, name desc",
        start=inputs.offset,
        page_length=inputs.limit + 1,
    )
    records = [shape(row, JOURNAL_FIELDS, outside=JOURNAL_OUTSIDE) for row in rows]
    return page(records, inputs.offset, inputs.limit)


async def get_journal_entry(inputs: GetJournalEntry, context: Context) -> dict[str, Any]:
    doc = await get_named(
        context, "Journal Entry", inputs.name, field="name", what="the journal entry", company=True
    )
    rows, cut = cut_rows(rows_of(doc, "accounts"))
    record = shape(doc, (*JOURNAL_FIELDS, *JOURNAL_DETAIL_FIELDS), outside=JOURNAL_OUTSIDE)
    outside = record.pop("outside_text")
    name = str(doc.get("name", inputs.name))
    return cut_texts(
        {
            **record,
            "accounts": [shape(r, JOURNAL_ROW_FIELDS, outside=JOURNAL_ROW_OUTSIDE) for r in rows],
            "url": form_url(context.settings.erpnext_public_url, "Journal Entry", name),
            "truncated": ["accounts"] if cut else [],
            "outside_text": outside,
        }
    )


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    return {"debit": row.get("debit"), "credit": row.get("credit"), "balance": row.get("balance")}


async def report_general_ledger(inputs: ReportGeneralLedger, context: Context) -> dict[str, Any]:
    # ERPNext's own checks don't name the input, and pass another company's account.
    if inputs.account is not None:
        await get_named(
            context, "Account", inputs.account, field="account", what="the account", company=True
        )
    if inputs.party is not None and inputs.party_type is not None:
        what = f"the {inputs.party_type.lower()}"
        await get_named(context, inputs.party_type, inputs.party, field="party", what=what)
    filters: dict[str, Any] = {
        "company": context.settings.company,
        "from_date": inputs.from_date.isoformat(),
        "to_date": inputs.to_date.isoformat(),
    }
    if inputs.account is not None:
        filters["account"] = [inputs.account]
    if inputs.party_type is not None:
        filters["party_type"] = inputs.party_type
    if inputs.party is not None:
        filters["party"] = [inputs.party]
    if inputs.voucher_no is not None:
        filters["voucher_no"] = inputs.voucher_no
    # As the desk sends them; without categorize_by, one row per GL entry.
    filters |= {"include_default_book_entries": 1, "show_remarks": 1}
    rows = await report_rows(context, "General Ledger", filters)
    # Opening first, total and closing last; their labels are translated, so by position.
    if len(rows) < 3 or any(r.get("posting_date") for r in (rows[0], rows[-2], rows[-1])):
        raise ErpnextError("ERPNext's General Ledger lacks its opening, total and closing rows.")
    opening, entries, closing = rows[0], rows[1:-2], rows[-1]
    # ERPNext reads the balance before from_date only with an account or a party; without,
    # its opening holds only the entries marked as opening.
    balanced = inputs.account is not None or inputs.party is not None
    debit = sum((decimal(e.get("debit")) for e in entries), Decimal(0))
    credit = sum((decimal(e.get("credit")) for e in entries), Decimal(0))
    shown = entries[inputs.offset : inputs.offset + inputs.limit + 1]
    records = [
        split_outside(
            {f: e.get(f) if f != "balance" or balanced else None for f in LEDGER_FIELDS},
            LEDGER_OUTSIDE,
        )
        for e in shown
    ]
    return {
        **page(records, inputs.offset, inputs.limit),
        "opening": _summary(opening),
        "totals": {"debit": debit, "credit": credit, "balance": debit - credit},
        "closing": _summary(closing),
        # An account or party in another currency switches ERPNext's amounts to it.
        "currency": opening.get("presentation_currency"),
    }


async def _fiscal_year(context: Context, from_date: date, to_date: date) -> str:
    """The fiscal year holding both dates, found as ERPNext finds it: enabled years assigned
    to the company first, then those assigned to none (get_fiscal_years)."""
    rows = await context.erpnext.get_list(
        "Fiscal Year",
        fields=("name", "year_start_date", "year_end_date", "companies.company"),
        filters=[
            ["disabled", "=", 0],
            ["year_start_date", "<=", from_date.isoformat()],
            ["year_end_date", ">=", from_date.isoformat()],
        ],
        order_by="year_start_date desc",
        start=0,
        page_length=MAX_FISCAL_YEAR_ROWS,
    )
    # With select only, ERPNext leaves out the child table and the non-search fields.
    if any(not row.get("year_end_date") for row in rows):
        raise ErpnextError("ERPNext's Fiscal Year list lacks the years' end dates.")
    years: dict[str, tuple[str, set[Any]]] = {}  # one row per company row
    for row in rows:
        _, companies = years.setdefault(
            str(row.get("name")), (str(row.get("year_end_date")), set())
        )
        companies.add(row.get("company"))
    own = [n for n, (_, c) in years.items() if context.settings.company in c]
    shared = [n for n, (_, c) in years.items() if c == {None}]
    if not own and not shared:
        raise Refusal(f"from_date: {from_date} is in no fiscal year of the assigned company.")
    name = (own or shared)[0]
    end = years[name][0]
    if to_date.isoformat() > end:
        raise Refusal(
            f"to_date: {to_date} is after the end of fiscal year {name} ({end}); give dates "
            "within one fiscal year."
        )
    return name


async def report_trial_balance(inputs: ReportTrialBalance, context: Context) -> dict[str, Any]:
    year = await _fiscal_year(context, inputs.from_date, inputs.to_date)
    filters: dict[str, Any] = {
        "company": context.settings.company,
        "fiscal_year": year,
        "from_date": inputs.from_date.isoformat(),
        "to_date": inputs.to_date.isoformat(),
        "show_zero_values": int(inputs.show_zero_values),
        # The desk's defaults; without them ERPNext leaves out period closing entries and
        # group accounts and doesn't net opening and closing.
        "with_period_closing_entry_for_opening": 1,
        "with_period_closing_entry_for_current_period": 1,
        "include_default_book_entries": 1,
        "show_net_values": 1,
        "show_group_accounts": 1,
    }
    rows = [r for r in await report_rows(context, "Trial Balance", filters) if r]
    # The total row comes last; it is the only one without is_group_account.
    if not rows or "is_group_account" in rows[-1]:
        raise ErpnextError("ERPNext's Trial Balance lacks its total row.")
    accounts = rows[:-1]
    totals = {
        f: sum((decimal(r.get(f)) for r in accounts if not r.get("parent_account")), Decimal(0))
        for f in BALANCE_VALUES
    }
    shown = accounts[inputs.offset : inputs.offset + inputs.limit + 1]
    records: list[dict[str, Any]] = [
        {
            "account": r.get("account"),
            "account_name": r.get("account_name"),
            "parent_account": r.get("parent_account"),
            "is_group": bool(r.get("is_group_account")),
            **{f: r.get(f) for f in BALANCE_VALUES},
            "outside_text": {},
        }
        for r in shown
    ]
    return {**page(records, inputs.offset, inputs.limit), "fiscal_year": year, "totals": totals}


OPERATIONS: list[Operation[Any]] = [
    Operation(
        name="list_accounts",
        title="List accounts",
        description=(
            "List the assigned company's accounts, ordered by ID. `search` matches part of the "
            "ID, the account name or the account number; `root_type` narrows to one of Asset, "
            "Liability, Equity, Income, Expense. Group accounts and disabled ones are left out "
            "unless `include_groups` or `include_disabled` is true. Use the IDs (`name`) as "
            "`account` elsewhere."
        ),
        kind="read",
        inputs=ListAccounts,
        run=list_accounts,
    ),
    Operation(
        name="list_cost_centers",
        title="List cost centres",
        description=(
            "List the assigned company's cost centres, ordered by ID. `search` matches part of "
            "the ID, the name or the number. Group cost centres and disabled ones are left out "
            "unless `include_groups` or `include_disabled` is true. Use the IDs (`name`) as "
            "`cost_center` elsewhere."
        ),
        kind="read",
        inputs=ListCostCenters,
        run=list_cost_centers,
    ),
    Operation(
        name="list_journal_entries",
        title="List journal entries",
        description=(
            "List the assigned company's journal entries, newest posting date first. Filter by "
            "`state` (draft, submitted, cancelled), `voucher_type` and posting date "
            "(`from_date`, `to_date`, YYYY-MM-DD)."
        ),
        kind="read",
        inputs=ListJournalEntries,
        run=list_journal_entries,
    ),
    Operation(
        name="get_journal_entry",
        title="Get journal entry",
        description=(
            "Get one journal entry of the assigned company by its exact number (`name`), with "
            "its account rows."
        ),
        kind="read",
        inputs=GetJournalEntry,
        run=get_journal_entry,
    ),
    Operation(
        name="report_general_ledger",
        title="General ledger",
        description=(
            "The assigned company's General Ledger from `from_date` to `to_date` (at most 366 "
            "days), one record per ledger entry, oldest first. Narrow it by `account`, "
            "`party_type` with `party`, or `voucher_no`. With `account` or `party`, `opening` "
            "is the balance before `from_date` and each record carries its running `balance`; "
            "without, `opening` holds only entries marked as opening (such as an Opening "
            "Entry), which are never among the records, and `balance` is null. `totals` cover "
            "every record, not only this page. Amounts are in the company's currency unless "
            "`currency` names the account's or party's. A busy ledger may be too large for a "
            "year without `account`: narrow it by account or period."
        ),
        kind="read",
        inputs=ReportGeneralLedger,
        run=report_general_ledger,
    ),
    Operation(
        name="report_trial_balance",
        title="Trial balance",
        description=(
            "The assigned company's Trial Balance from `from_date` to `to_date`, which must lie "
            "in one fiscal year (named in `fiscal_year`): per account its opening, the period's "
            "debit and credit, and its closing, group accounts included (`is_group`). Accounts "
            "without values are left out unless `show_zero_values` is true. `totals` sum the "
            "top-level accounts."
        ),
        kind="read",
        inputs=ReportTrialBalance,
        run=report_trial_balance,
    ),
]
