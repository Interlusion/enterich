"""The operations, one module per accounting area (REQ-003 to REQ-007).

Each operation publishes its strict input schema to the SDK, but validates
its arguments itself, so a refused input is logged like any other outcome
and the error names the input (REQ-001-PRS-F008, REQ-002-PRS-NF008). It
returns errors as results, so the agent gets Erpel's text unchanged.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from itertools import islice
from typing import Any, Literal, cast

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.mcpserver.tools import Tool
from mcp.server.mcpserver.utilities.func_metadata import ArgModelBase, FuncMetadata
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ConfigDict, ValidationError

from erpel import erpnext, log
from erpel.config import Settings
from erpel.erpnext import MAX_MESSAGE, Erpnext, ErpnextError, Refused
from erpel.shapes import OUTSIDE_TEXT_NOTE, Inputs, to_text

OPERATION_TIMEOUT = 60.0
MAX_LOGGED_STRING = 200
MAX_LOGGED_ITEMS = 100
UNEXPECTED = "Erpel failed unexpectedly; the operator finds the details in Erpel's log."

type Kind = Literal["read", "create", "update"]


class Refusal(Exception):  # noqa: N818 - a refusal, not a fault of Erpel's
    """Erpel's own refusal; `str()` is the text for the agent."""


@dataclass(frozen=True)
class Context:
    settings: Settings
    erpnext: Erpnext


@dataclass(frozen=True)
class Operation[I: Inputs]:
    name: str
    title: str
    description: str
    kind: Kind
    inputs: type[I]
    run: Callable[[I, Context], Awaitable[dict[str, Any]]]


def operations() -> list[Operation[Any]]:
    from erpel.tools import master_data

    return [*master_data.OPERATIONS]


def names() -> tuple[str, ...]:
    """Every operation Erpel offers; `ERPEL_TOOLS` may only name these."""
    return tuple(sorted(op.name for op in operations()))


def build(settings: Settings, client: Erpnext) -> list[Tool]:
    """The SDK tools for the operations `ERPEL_TOOLS` allows (REQ-001-PRS-F011)."""
    context = Context(settings, client)
    offered = set(settings.tools)
    return [_tool(op, context) for op in operations() if op.name in offered]


class _AnyArguments(ArgModelBase):
    """Hands every argument through; the operation's own model validates them."""

    model_config = ConfigDict(extra="allow")

    def model_dump_one_level(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


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
    async def handler(**arguments: Any) -> CallToolResult:
        return await _run(op, context, arguments)

    return Tool(
        fn=handler,
        name=op.name,
        title=op.title,
        description=f"{op.description}\n\n{OUTSIDE_TEXT_NOTE}",
        parameters=op.inputs.model_json_schema(),
        fn_metadata=FuncMetadata(arg_model=_AnyArguments),
        is_async=True,
        context_kwarg=None,
        annotations=_annotations(op),
    )


async def get_named(
    context: Context, doctype: str, name: str, *, field: str, what: str
) -> dict[str, Any]:
    """The document a name input names; unknown or unpermitted per REQ-001-PRS-F009."""
    try:
        return await context.erpnext.get_doc(doctype, name)
    except Refused as refused:
        if refused.status in (403, 404):
            raise Refusal(
                f"{field}: {what} {name!r} doesn't exist, "
                "or the agent user isn't permitted to read it."
            ) from None
        raise


async def _run(op: Operation[Any], context: Context, arguments: dict[str, Any]) -> CallToolResult:
    """Run one operation; the result goes back as it is, so no SDK prefix lengthens an error."""
    started = time.monotonic()
    with erpnext.metered() as meter:
        try:
            text, outcome = await _attempt(op, context, arguments)
        except Exception as exc:  # noqa: BLE001 - logged here with the operation
            log.failure(exc, context.settings.secrets, operation=op.name)
            text, outcome = UNEXPECTED, {"refusal": UNEXPECTED}
        _log(op, arguments, started, meter, outcome)
    return CallToolResult(
        content=[TextContent(type="text", text=text)], is_error="refusal" in outcome
    )


async def _attempt(
    op: Operation[Any], context: Context, arguments: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    try:
        inputs = op.inputs.model_validate(arguments)
    except ValidationError as exc:
        return _refused(_validation_text(exc))
    try:
        with anyio.fail_after(OPERATION_TIMEOUT):
            result = await op.run(inputs, context)
    except TimeoutError:
        return _refused(f"The operation took longer than {OPERATION_TIMEOUT:g} seconds.")
    except (Refusal, ErpnextError) as exc:
        return _refused(str(exc))
    text = to_text(result)
    if text is None:
        return _refused(
            "The result would exceed 100,000 characters; narrow the request "
            "(a search, a filter or a smaller limit)."
        )
    return text, _outcome(op, result)


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
) -> None:
    access = get_access_token()
    claims = access.claims if access and access.claims else {}
    log.event(
        "operation",
        logging.WARNING if "refusal" in outcome else logging.INFO,
        operation=op.name,
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
