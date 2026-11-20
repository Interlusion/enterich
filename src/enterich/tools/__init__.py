"""The operations, one module per accounting area (REQ-003 to REQ-007).

Each operation publishes its strict input schema to the SDK, but validates
its arguments itself, so a refused input is logged like any other outcome
and the error names the input (REQ-001-PRS-F008, REQ-002-PRS-NF008). It
returns errors as results, so the agent gets Enterich's text unchanged.
"""

import html
import json
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from itertools import islice
from typing import Any, Literal, cast

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver import Context as Request
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ConfigDict, ValidationError

from enterich import erpnext, log, shapes
from enterich.config import Settings
from enterich.erpnext import MAX_MESSAGE, Erpnext, ErpnextError, Refused
from enterich.shapes import (
    OUTSIDE_TEXT_NOTE,
    Inputs,
    cut_rows,
    cut_texts,
    form_url,
    rows_of,
    shape,
    to_text,
)

OPERATION_TIMEOUT = 60.0
MAX_LOGGED_STRING = 200
MAX_LOGGED_ITEMS = 100
UNEXPECTED = "Enterich failed unexpectedly; the operator finds the details in Enterich's log."
# A draft result's lists that aren't its child tables
KEPT_LISTS = frozenset({"warnings", "truncated"})
# The fields of the saved draft every create or update result has (REQ-001's Results)
SAVED_FIELDS = ("name", "modified", "status", "docstatus", "company")
# The inputs that name an update's draft, those drafts.DraftUpdate declares; all others are
# its changes
UPDATE_KEYS = ("name", "modified")
# All the fields every create or update result has; all else can be left out
DRAFT_RESULT_FIELDS = frozenset({*SAVED_FIELDS, "url", *KEPT_LISTS})
# The keyword the SDK hands a tool its request under; the client's arguments come in one
# dict beside it, so a client argument of that name stays an argument
REQUEST = "enterich_request"

type Kind = Literal["read", "create", "update"]


class Refusal(Exception):  # noqa: N818 - a refusal, not a fault of Enterich's
    """Enterich's own refusal; `str()` is the text for the agent."""


@dataclass(frozen=True)
class Context:
    settings: Settings
    erpnext: Erpnext
    # A lock per DocType, held by a create from its count of drafts per hour to its insert
    # (REQ-001-PRS-F019)
    creating: defaultdict[str, anyio.Lock] = field(
        default_factory=lambda: defaultdict[str, anyio.Lock](anyio.Lock)
    )


@dataclass(frozen=True)
class Operation[I: Inputs]:
    name: str
    title: str
    description: str
    kind: Kind
    inputs: type[I]
    run: Callable[[I, Context], Awaitable[dict[str, Any]]]
    doctype: str | None = None  # the DocType a create or update writes


def operations() -> list[Operation[Any]]:
    from enterich.tools import (
        bank_and_cash,
        master_data,
        order_to_cash,
        procure_to_pay,
        record_to_report,
    )

    return [
        *master_data.OPERATIONS,
        *order_to_cash.OPERATIONS,
        *procure_to_pay.OPERATIONS,
        *record_to_report.OPERATIONS,
        *bank_and_cash.OPERATIONS,
    ]


def names() -> tuple[str, ...]:
    """Every operation Enterich offers; `ENTERICH_TOOLS` may only name these."""
    return tuple(sorted(op.name for op in operations()))


def build(settings: Settings, client: Erpnext) -> list[Tool]:
    """The SDK tools for the operations `ENTERICH_TOOLS` allows (REQ-001-PRS-F011)."""
    context = Context(settings, client)
    offered = set(settings.tools)
    return [_tool(op, context) for op in operations() if op.name in offered]


def _origin(op: Operation[Any], call: str, inputs: Inputs) -> str:
    """REQ-001-PRS-F015: the operation, its call, and an update's given inputs by name."""
    origin = f"{op.name}, call {call}"
    if op.kind == "update":
        given = inputs.model_dump(exclude_none=True)
        named = [f for f in type(inputs).model_fields if f in given and f not in UPDATE_KEYS]
        origin += f"; given {', '.join(named)}"
    return origin + "."


async def _comment(
    context: Context,
    op: Operation[Any],
    name: str,
    origin: str,
    warnings: list[str],
    deadline: float,
) -> list[str]:
    """REQ-001-PRS-F015: one comment with the origin and the warnings, as plain text, by the
    operation's deadline; a failure is one more warning. Only a refusal says it wasn't added:
    after a late or lost answer ERPNext may have stored it."""
    # The content is HTML: each line escaped, one per line
    lines = [origin, *warnings]
    content = "Enterich: " + "<br>".join(html.escape(line, quote=False) for line in lines)
    with anyio.move_on_after(deadline - time.monotonic()) as scope:
        try:
            await context.erpnext.add_comment(str(op.doctype), name, content)
        except Refused as refused:
            return [*warnings, f"Enterich's comment couldn't be added to the draft: {refused}"]
        except ErpnextError as exc:
            return [*warnings, f"Enterich's comment may be missing from the draft: {exc}"]
    if scope.cancelled_caught:
        return [
            *warnings,
            f"Enterich's comment couldn't be added to the draft within the operation's "
            f"{OPERATION_TIMEOUT:g} seconds; it may be missing.",
        ]
    return warnings


class _AnyArguments(ArgModelBase):
    """Hands every argument through; the operation's own model validates them."""

    model_config = ConfigDict(extra="allow")

    def model_dump_one_level(self) -> dict[str, Any]:
        return {"arguments": dict(self.model_extra or {})}


def _annotations(op: Operation[Any]) -> ToolAnnotations:
    # REQ-001-PRS-NF002: hints only; no decision reads them.
    if op.kind == "read":
        return ToolAnnotations(title=op.title, read_only_hint=True, open_world_hint=False)
    return ToolAnnotations(
        title=op.title,
        read_only_hint=False,
        destructive_hint=op.kind == "update",
        idempotent_hint=op.kind == "update",
        open_world_hint=False,
    )


def _tool(op: Operation[Any], context: Context) -> Tool:
    async def handler(
        arguments: dict[str, Any], enterich_request: Request[Any, Any] | None = None
    ) -> CallToolResult:
        request_id = enterich_request.request_id if enterich_request else None
        return await _run(op, context, arguments, request_id)

    return Tool(
        fn=handler,
        name=op.name,
        title=op.title,
        description=f"{op.description}\n\n{OUTSIDE_TEXT_NOTE}",
        parameters=op.inputs.model_json_schema(),
        fn_metadata=FuncMetadata(arg_model=_AnyArguments),
        is_async=True,
        context_kwarg=REQUEST,
        annotations=_annotations(op),
    )


def unknown_name(field: str, what: str, name: str) -> Refusal:
    """The answer for a name that doesn't exist or isn't permitted (REQ-001-PRS-F009)."""
    return Refusal(
        f"{field}: {what} {name!r} doesn't exist, or the agent user isn't permitted to read it."
    )


async def get_named(
    context: Context, doctype: str, name: str, *, field: str, what: str, company: bool = False
) -> dict[str, Any]:
    """The document a name input names; unknown or unpermitted per REQ-001-PRS-F009.

    With `company`, another company's document answers the same (REQ-001-PRS-F007).
    """
    unknown = unknown_name(field, what, name)
    try:
        doc = await context.erpnext.get_doc(doctype, name)
    except Refused as refused:
        if refused.status in (403, 404):
            raise unknown from None
        raise
    if company and doc.get("company") != context.settings.company:
        raise unknown
    return doc


@dataclass(frozen=True)
class Table:
    """A child table as a get returns it: its catalogued fields, outside text apart."""

    fields: Sequence[str]
    outside: AbstractSet[str] = frozenset()


async def get_document(
    context: Context,
    doctype: str,
    name: str,
    *,
    what: str,
    fields: Sequence[str],
    outside: AbstractSet[str] = frozenset(),
    flags: AbstractSet[str] = frozenset(),
    tables: Mapping[str, Table],
    derived: Mapping[str, Callable[[dict[str, Any]], tuple[list[dict[str, Any]], bool]]]
    | None = None,
) -> dict[str, Any]:
    """A document of the assigned company with its child tables, each cut at 100 rows, and
    the tables `derived` builds from the document with whether they were cut; its link and
    its texts cut (REQ-001-PRS-F007, REQ-001-PRS-F009, REQ-001-PRS-NF003)."""
    doc = await get_named(context, doctype, name, field="name", what=what, company=True)
    record = shape(doc, fields, outside=outside, flags=flags)
    outside_text = record.pop("outside_text")
    truncated: list[str] = []
    for table, spec in tables.items():
        rows, cut = cut_rows(rows_of(doc, table))
        record[table] = [shape(row, spec.fields, outside=spec.outside) for row in rows]
        if cut:
            truncated.append(table)
    for table, build in (derived or {}).items():
        record[table], cut = build(doc)
        if cut:
            truncated.append(table)
    url = form_url(context.settings.erpnext_public_url, doctype, str(doc.get("name", name)))
    return cut_texts({**record, "url": url, "truncated": truncated, "outside_text": outside_text})


async def report_rows(
    context: Context, report: str, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    """A report's rows that are records; a prepared report is refused without waiting, a
    snapshot report as not current, and a total row Frappe appends as a list is left out."""
    answer = await context.erpnext.run_report(report, filters)
    if answer.get("prepared_report"):
        raise Refusal(
            f"ERPNext runs {report} as a prepared report, and Enterich doesn't wait for one; the "
            "operator can turn that off (see Enterich's configuration guide)."
        )
    if answer.get("snapshot_report"):
        raise Refusal(
            f"ERPNext runs {report} as a snapshot report on data synced earlier, which Enterich "
            "doesn't take for current data; the operator can turn that off (see Enterich's "
            "configuration guide)."
        )
    listed = cast("list[Any]", answer["result"])
    return [cast("dict[str, Any]", row) for row in listed if isinstance(row, dict)]


async def _run(
    op: Operation[Any], context: Context, arguments: dict[str, Any], request_id: str | None
) -> CallToolResult:
    """Run one operation; the result goes back as it is, so no SDK prefix lengthens an error."""
    started = time.monotonic()
    call = secrets.token_hex(6)  # REQ-002-PRS-NF008
    with erpnext.metered() as meter:
        try:
            text, outcome = await _attempt(op, context, arguments, call, meter)
        except Exception as exc:  # noqa: BLE001 - logged here with the operation
            log.failure(exc, context.settings.secrets, operation=op.name, call=call)
            text, outcome = UNEXPECTED, {"refusal": UNEXPECTED}
        _log(op, arguments, started, meter, outcome, call, request_id)
    return CallToolResult(
        content=[TextContent(type="text", text=text)], is_error="refusal" in outcome
    )


async def _attempt(
    op: Operation[Any],
    context: Context,
    arguments: dict[str, Any],
    call: str,
    meter: erpnext.Meter,
) -> tuple[str, dict[str, Any]]:
    try:
        inputs = op.inputs.model_validate(arguments)
    except ValidationError as exc:
        return _refused(_validation_text(exc))
    deadline = time.monotonic() + OPERATION_TIMEOUT
    try:
        with anyio.fail_after(OPERATION_TIMEOUT):
            result = await op.run(inputs, context)
    except Exception as exc:
        if meter.written is None or op.kind == "read":
            if isinstance(exc, TimeoutError):
                return _refused(f"The operation took longer than {OPERATION_TIMEOUT:g} seconds.")
            if isinstance(exc, Refusal | ErpnextError):
                return _refused(str(exc))
            raise
        # ERPNext saved the draft: it is returned, never as refused (REQ-001-PRS-F015)
        result = _written(context, op, meter, exc, call)
    if op.kind == "read":
        text = to_text(result)
        if text is None:
            return _refused(
                f"The result would exceed {shapes.MAX_RESULT_CHARS:,} characters: narrow a list "
                "or report (a search, a filter or a smaller limit); a single document this large "
                "is too large to return."
            )
        return text, _outcome(op, result)
    # What a check noted on the way joins the warnings; a result of _written holds it already
    noted = [w for w in meter.noted if w not in result["warnings"]]
    result["warnings"] = [*result["warnings"], *noted]
    # The draft is written: it gets its comment, and the agent its number, whatever its size
    origin = _origin(op, call, inputs)
    result["warnings"] = await _comment(
        context, op, str(result["name"]), origin, result["warnings"], deadline
    )
    return _write_text(result), _outcome(op, result)


def _written(
    context: Context, op: Operation[Any], meter: erpnext.Meter, exc: Exception, call: str
) -> dict[str, Any]:
    """The fields every draft result has, of the draft ERPNext saved before `exc`, with the
    warnings the operation knew before its write."""
    saved = meter.written or {}
    if isinstance(exc, TimeoutError):
        failure = f"the operation took longer than {OPERATION_TIMEOUT:g} seconds"
    elif isinstance(exc, Refusal | ErpnextError):
        failure = str(exc)
    else:
        log.failure(exc, context.settings.secrets, operation=op.name, call=call)
        failure = UNEXPECTED
    name = str(saved.get("name"))
    return {
        **{k: saved[k] for k in SAVED_FIELDS if k in saved},
        "url": form_url(context.settings.erpnext_public_url, str(op.doctype), name),
        "warnings": [
            *meter.warned,
            *meter.noted,
            f"ERPNext saved the draft, but Enterich couldn't build the rest of this result "
            f"({failure.rstrip('.')}). Read the draft to see it.",
        ],
        "truncated": [],
    }


def _write_text(result: dict[str, Any]) -> str:
    """A create or update result, without its child tables when it would be too large with
    them, and without all but the fields every draft result has when it still would
    (REQ-001-PRS-NF003); its warnings stay, the comment's among them."""
    text = to_text(result)
    if text is not None:
        return text
    tables = [k for k, v in result.items() if isinstance(v, list) and k not in KEPT_LISTS]
    rest = [k for k in result if k not in DRAFT_RESULT_FIELDS]
    slim = result
    for left_out in (tables, rest):
        if left_out:
            slim = _without(result, left_out)
            if (text := to_text(slim)) is not None:
                return text
    # What is left is short, and the warnings are few: no draft result gets here
    return json.dumps(slim, ensure_ascii=False, default=str)


def _without(result: dict[str, Any], left_out: list[str]) -> dict[str, Any]:
    cut = cast("list[str]", result.get("truncated") or [])
    note = (
        f"This result leaves out the draft's {', '.join(left_out)}: with them it would exceed "
        f"{shapes.MAX_RESULT_CHARS:,} characters. Read the draft to see them."
    )
    return {
        **{k: v for k, v in result.items() if k not in left_out},
        "truncated": [*(t for t in cut if t.split(".")[0] not in left_out), *left_out],
        "warnings": [*result["warnings"], note],
    }


def _refused(text: str) -> tuple[str, dict[str, Any]]:
    if len(text) > MAX_MESSAGE:
        text = text[: MAX_MESSAGE - 1] + "…"
    return text, {"refusal": text}


def _outcome(op: Operation[Any], result: dict[str, Any]) -> dict[str, Any]:
    if op.kind != "read":
        return {"document": result["name"]}
    records = result.get("records")
    return {"rows": len(records) if isinstance(records, list) else 1}  # pyright: ignore[reportUnknownArgumentType]


def _validation_text(exc: ValidationError) -> str:
    problems: list[str] = []
    for error in exc.errors(include_url=False, include_input=False):
        where = ".".join(str(part) for part in error["loc"]) or "input"
        problems.append(f"{where}: {error['msg']}")
    return "Invalid input. " + "; ".join(problems)


def _log(
    op: Operation[Any],
    arguments: dict[str, Any],
    started: float,
    meter: erpnext.Meter,
    outcome: dict[str, Any],
    call: str,
    request_id: str | None,
) -> None:
    access = get_access_token()
    claims = access.claims if access and access.claims else {}
    log.event(
        "operation",
        logging.WARNING if "refusal" in outcome else logging.INFO,
        operation=op.name,
        call=call,
        request_id=_cut(request_id),
        arguments=_cut(arguments),
        sub=access.subject if access else None,
        sid=claims.get("sid"),
        outcome=outcome,
        duration=round(time.monotonic() - started, 3),
        erpnext_calls=meter.calls,
        erpnext_duration=round(meter.seconds, 3),
    )


def _cut(value: Any) -> Any:
    """Arguments for the log: strings and keys cut to 200 characters, lists and objects
    to their first 100 items."""
    if isinstance(value, str):
        return value[:MAX_LOGGED_STRING]
    if isinstance(value, dict):
        pairs = cast("dict[Any, Any]", value).items()
        return {str(k)[:MAX_LOGGED_STRING]: _cut(v) for k, v in islice(pairs, MAX_LOGGED_ITEMS)}
    if isinstance(value, list):
        return [_cut(v) for v in islice(cast("list[Any]", value), MAX_LOGGED_ITEMS)]
    return value
