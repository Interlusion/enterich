"""Record to report: accounts, cost centres, journal entries, the General Ledger and the
Trial Balance (REQ-006)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import AfterValidator, Field, model_validator

from enterich.erpnext import ErpnextError
from enterich.shapes import (
    Amount,
    Day,
    Flag,
    Inputs,
    Limit,
    Modified,
    Name,
    Offset,
    Remarks,
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
    today,
)
from enterich.tools import (
    Context,
    Operation,
    Refusal,
    drafts,
    get_named,
    report_rows,
)

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
JOURNAL_DRAFT_FIELDS = ("posting_date", "total_debit", "total_credit")
JOURNAL_MATCH = "posting date and rows"
# The most rounding to a currency's precision (2 or 3 places) moves an amount.
ROUNDING = Decimal("0.005")
# The bank's reference: free text, not a name (ERPNext's Data field)
ChequeNo = Annotated[str, Field(min_length=1, max_length=140)]

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


class JournalEntryRow(Inputs):
    account: Name
    debit: Amount | None = None
    credit: Amount | None = None
    party_type: Literal["Customer", "Supplier"] | None = None
    party: Name | None = None
    cost_center: Name | None = None
    reference_type: Literal["Sales Invoice", "Purchase Invoice"] | None = None
    reference_name: Name | None = None
    user_remark: Remarks | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        """REQ-006-PRS-F006, per row."""
        if bool(self.debit) == bool(self.credit):
            raise ValueError("give exactly one of debit and credit, above 0")
        if (self.party_type is None) != (self.party is None):
            raise ValueError("party_type and party come together")
        if (self.reference_type is None) != (self.reference_name is None):
            raise ValueError("reference_type and reference_name come together")
        return self


def _balanced(rows: list[JournalEntryRow]) -> list[JournalEntryRow]:
    """REQ-006-PRS-F006: debits and credits equal as exact decimals."""
    debit = sum((r.debit or Decimal(0) for r in rows), Decimal(0))
    credit = sum((r.credit or Decimal(0) for r in rows), Decimal(0))
    if debit != credit:
        raise ValueError(f"the debits ({debit}) and the credits ({credit}) must be equal")
    return rows


JournalEntryRows = Annotated[
    list[JournalEntryRow], Field(min_length=2, max_length=20), AfterValidator(_balanced)
]


class CreateDraftJournalEntry(Inputs):
    posting_date: Day | None = None
    cheque_no: ChequeNo | None = None
    cheque_date: Day | None = None
    user_remark: Remarks | None = None
    accounts: JournalEntryRows
    allow_duplicate: Flag = False

    @model_validator(mode="after")
    def _reference(self) -> Self:
        _reference_rule(self.cheque_no, self.cheque_date)
        return self


class UpdateDraftJournalEntry(Inputs):
    name: Name
    modified: Modified
    posting_date: Day | None = None
    cheque_no: ChequeNo | Literal[""] | None = None
    cheque_date: Day | None = None
    user_remark: Remarks | None = None
    accounts: JournalEntryRows | None = None

    @model_validator(mode="after")
    def _changes(self) -> Self:
        given = self.model_dump(exclude={"name", "modified"}, exclude_none=True)
        if not given:
            raise ValueError(
                "give at least one of posting_date, cheque_no, cheque_date, user_remark, accounts"
            )
        return self


def _reference_rule(number: Any, day: Any) -> None:
    """REQ-006-PRS-F006: ERPNext refuses a reference number without its date at every save,
    a date without its number on submit."""
    if number and not day:
        raise ValueError("cheque_date: a reference number (cheque_no) needs its date")
    if day and not number:
        raise ValueError("cheque_no: a reference date (cheque_date) needs its number")


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


def _journal_body(inputs: CreateDraftJournalEntry | UpdateDraftJournalEntry) -> dict[str, Any]:
    """The catalogue's "Sent to ERPNext" for the given inputs: rows with the account-currency
    fields, the only ones ERPNext writes; a cleared reference clears its date."""
    doc: dict[str, Any] = {}
    if inputs.posting_date is not None:
        doc["posting_date"] = inputs.posting_date.isoformat()
    if inputs.cheque_no is not None:
        doc["cheque_no"] = inputs.cheque_no
        if inputs.cheque_no == "":
            doc["cheque_date"] = None
    if inputs.cheque_date is not None:
        doc["cheque_date"] = inputs.cheque_date.isoformat()
    if inputs.user_remark is not None:
        doc["user_remark"] = inputs.user_remark
    if inputs.accounts is not None:
        doc["accounts"] = [_journal_row(row) for row in inputs.accounts]
    return doc


def _journal_row(row: JournalEntryRow) -> dict[str, Any]:
    names = {"debit": "debit_in_account_currency", "credit": "credit_in_account_currency"}
    return {names.get(k, k): v for k, v in row.model_dump(exclude_none=True).items()}


async def _journal_duplicates(
    context: Context, posting_date: date, rows: Sequence[JournalEntryRow]
) -> list[str]:
    """REQ-006-PRS-F007: drafts of the assigned company on the posting date with the same
    rows (account, debit, credit), in any order."""
    found = await context.erpnext.get_list(
        "Journal Entry",
        fields=(
            "name",
            "accounts.account",
            "accounts.debit_in_account_currency",
            "accounts.credit_in_account_currency",
        ),
        filters=[
            ["company", "=", context.settings.company],
            ["docstatus", "=", 0],
            ["posting_date", "=", posting_date.isoformat()],
        ],
        order_by="name asc",
        start=0,
        page_length=drafts.MAX_DUPLICATE_ROWS,
    )
    entries: dict[str, list[tuple[str, Decimal, Decimal]]] = {}
    for row in found:
        stored = entries.setdefault(str(row.get("name")), [])
        if row.get("account") is not None:
            debit = decimal(row.get("debit_in_account_currency"))
            credit = decimal(row.get("credit_in_account_currency"))
            stored.append((str(row["account"]), debit, credit))
    wanted = [(r.account, r.debit or Decimal(0), r.credit or Decimal(0)) for r in rows]
    return sorted(name for name, stored in entries.items() if _same_rows(wanted, stored))


def _same_rows(
    wanted: list[tuple[str, Decimal, Decimal]], stored: list[tuple[str, Decimal, Decimal]]
) -> bool:
    """The given rows as ERPNext stores them: each amount rounded to the currency's
    precision, which moves it by at most ROUNDING. Rounding keeps the order, so the rows
    pair up sorted."""
    return len(wanted) == len(stored) and all(
        w[0] == s[0] and abs(w[1] - s[1]) <= ROUNDING and abs(w[2] - s[2]) <= ROUNDING
        for w, s in zip(sorted(wanted), sorted(stored), strict=True)
    )


def _rounding_warning(saved: dict[str, Any]) -> list[str]:
    """REQ-006-PRS-F008: ERPNext rounds each row to the currency's precision and checks the
    balance only on submit."""
    debit, credit = decimal(saved.get("total_debit")), decimal(saved.get("total_credit"))
    if debit == credit:
        return []
    return [
        f"ERPNext rounded the rows to the currency's precision and saved a total debit of "
        f"{drafts.plain(debit)} against a total credit of {drafts.plain(credit)}; adjust the "
        "rows so that they balance, or ERPNext refuses to submit the entry."
    ]


async def _journal_result(
    context: Context, saved: dict[str, Any], warnings: list[str]
) -> dict[str, Any]:
    name = str(saved.get("name"))
    record = shape(saved, ("name", "modified", "docstatus", "company", *JOURNAL_DRAFT_FIELDS))
    return {
        **record,
        "row_count": len(rows_of(saved, "accounts")),
        "url": form_url(context.settings.erpnext_public_url, "Journal Entry", name),
        "warnings": await drafts.comment(context, "Journal Entry", name, warnings),
        "truncated": [],
    }


async def create_draft_journal_entry(
    inputs: CreateDraftJournalEntry, context: Context
) -> dict[str, Any]:
    posting_date = inputs.posting_date or today(context.settings.timezone)
    # ERPNext sets no posting date itself; only the form does.
    doc = {**_journal_body(inputs), "posting_date": posting_date.isoformat()}
    matches = await _journal_duplicates(context, posting_date, inputs.accounts)
    if matches and not inputs.allow_duplicate:
        raise drafts.refuse_duplicates(matches, JOURNAL_MATCH)
    saved = await context.erpnext.insert(
        "Journal Entry",
        {
            **doc,
            "voucher_type": "Journal Entry",
            "multi_currency": 0,
            "company": context.settings.company,
            "docstatus": 0,
        },
    )
    warnings = [drafts.duplicate_warning(matches, JOURNAL_MATCH)] if matches else []
    warnings += _rounding_warning(saved)
    return await _journal_result(context, saved, warnings)


async def update_draft_journal_entry(
    inputs: UpdateDraftJournalEntry, context: Context
) -> dict[str, Any]:
    # Enterich changes only entries of the voucher type it creates.
    stored = await drafts.editable(
        context,
        "Journal Entry",
        inputs.name,
        inputs.modified,
        "the journal entry",
        only={"voucher_type": "Journal Entry"},
    )
    if stored.get("multi_currency"):
        raise Refusal(
            f"name: {inputs.name} has accounts in several currencies; Enterich changes only "
            "journal entries in the company's currency."
        )
    # The rules on the draft as it will be saved: stored values where none are given.
    if inputs.accounts is None:
        debit, credit = decimal(stored.get("total_debit")), decimal(stored.get("total_credit"))
        if debit != credit:
            raise Refusal(
                f"accounts: the draft's rows don't balance (total debit {drafts.plain(debit)} "
                f"against total credit {drafts.plain(credit)}); give the rows."
            )
    number = stored.get("cheque_no") if inputs.cheque_no is None else inputs.cheque_no
    if inputs.cheque_date is not None:
        day: Any = inputs.cheque_date
    else:
        day = None if inputs.cheque_no == "" else stored.get("cheque_date")
    if day and not number and inputs.cheque_date is None:
        raise Refusal(
            f"cheque_no: the draft has a reference date ({day}) without a reference number; "
            "give cheque_no, or an empty cheque_no to clear the date."
        )
    try:
        _reference_rule(number, day)
    except ValueError as exc:
        raise Refusal(str(exc)) from None
    saved = await drafts.save_update(
        context,
        "Journal Entry",
        inputs.name,
        {**_journal_body(inputs), "modified": inputs.modified},
    )
    return await _journal_result(context, saved, _rounding_warning(saved))


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
    Operation(
        name="create_draft_journal_entry",
        title="Create draft journal entry",
        description=(
            "Create a draft journal entry (voucher type Journal Entry) of the assigned "
            "company; a person reviews and submits it in ERPNext. Give 2 to 20 `accounts` "
            "rows, each with exactly one of `debit` and `credit`; debits and credits must be "
            "equal. Accounts are in the company's currency. A receivable or payable account "
            "needs `party_type` and `party`; ERPNext saves a party on another account but "
            "refuses it on submit. A row referencing an invoice carries its party and its "
            "receivable or payable account; `reference_type` and `reference_name` come "
            "together. `cheque_no` and `cheque_date` (the bank's reference and its date) come "
            "together. `posting_date` defaults to today. A draft "
            "with the same posting date and rows is refused unless `allow_duplicate` is true. "
            "After an error or a timeout, list the drafts (`list_journal_entries` with `state` "
            "draft) before creating again: the first may have been saved."
        ),
        kind="create",
        inputs=CreateDraftJournalEntry,
        run=create_draft_journal_entry,
    ),
    Operation(
        name="update_draft_journal_entry",
        title="Update draft journal entry",
        description=(
            "Change a draft journal entry (voucher type Journal Entry) of the assigned company. "
            "Give its `name` and its `modified` as last read; a draft changed since is "
            "refused. Give only what changes: `accounts` replace all rows, under the same "
            "rules as on create; without them, the draft's rows must balance. A draft with "
            "accounts in several currencies can't be changed. An empty `user_remark` clears "
            "it, and an empty `cheque_no` clears it with `cheque_date`."
        ),
        kind="update",
        inputs=UpdateDraftJournalEntry,
        run=update_draft_journal_entry,
    ),
]
