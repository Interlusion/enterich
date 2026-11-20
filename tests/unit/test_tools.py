"""Running an operation: REQ-001-PRS-F008 (tool errors), REQ-002-PRS-NF008
(operation and error lines), with operations made up for the test."""

import json
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from enterich import tools
from enterich.erpnext import Erpnext
from enterich.shapes import Inputs
from enterich.tools import Context, Kind, Operation, drafts
from tests.conftest import Logs
from tests.fakes.erpnext import COMMENT_METHOD, FakeErpnext, error
from tests.fakes.settings import API_SECRET, settings

pytestmark = pytest.mark.anyio


class Nothing(Inputs):
    pass


class Strict(BaseModel):
    value: int


async def call(
    monkeypatch: pytest.MonkeyPatch,
    run: Any,
    kind: Kind = "read",
    arguments: dict[str, Any] | None = None,
    erp: FakeErpnext | None = None,
) -> tuple[bool, str]:
    op = Operation(
        name="try_it",
        title="Try it",
        description="A test.",
        kind=kind,
        inputs=Nothing,
        run=run,
        doctype=None if kind == "read" else "Sales Invoice",
    )
    monkeypatch.setattr(tools, "operations", lambda: [op])
    s = settings(tools="try_it")
    [tool] = tools.build(s, Erpnext(s, (erp or FakeErpnext()).transport()))
    result = await tool.run(arguments or {}, context=None, convert_result=True)  # pyright: ignore[reportArgumentType]
    assert isinstance(result, CallToolResult)
    [content] = result.content
    assert isinstance(content, TextContent)
    return result.is_error, content.text


async def test_a_crash_writes_an_error_line_and_tells_the_agent_nothing_of_it(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def crash(inputs: Nothing, context: Context) -> dict[str, Any]:
        raise RuntimeError(f"boom with {API_SECRET}")

    error, text = await call(monkeypatch, crash)
    assert error
    assert "boom" not in text
    [line] = logs.events("error")
    assert line["operation"] == "try_it"
    assert line["exception"] == "RuntimeError"
    assert "boom" in line["message"]
    assert "RuntimeError" in line["traceback"]
    [operation] = logs.events("operation")
    assert operation["outcome"] == {"refusal": text}
    assert line["call"] == operation["call"]


async def test_a_validation_error_inside_an_operation_is_a_crash_not_invalid_input(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def misshaped(inputs: Nothing, context: Context) -> dict[str, Any]:
        Strict.model_validate({"value": "many"})
        return {}

    error, text = await call(monkeypatch, misshaped)
    assert error
    assert "Invalid input" not in text
    assert "value" not in text
    assert len(logs.events("error")) == 1


async def test_the_agent_gets_enterichs_text_without_a_prefix(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def refuse(inputs: Nothing, context: Context) -> dict[str, Any]:
        raise tools.Refusal("x" * 1000)

    error, text = await call(monkeypatch, refuse)
    assert error
    assert text.startswith("xxx")
    assert len(text) <= 300
    [operation] = logs.events("operation")
    assert operation["outcome"] == {"refusal": text}


async def test_a_refusal_of_300_is_kept_whole_and_one_of_301_is_cut_to_300(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    """REQ-001-PRS-F008: only a text over 300 characters is cut, to exactly 300."""

    async def fits(inputs: Nothing, context: Context) -> dict[str, Any]:
        raise tools.Refusal("x" * 300)

    async def over(inputs: Nothing, context: Context) -> dict[str, Any]:
        raise tools.Refusal("y" * 301)

    _, whole = await call(monkeypatch, fits)
    _, cut = await call(monkeypatch, over)
    assert whole == "x" * 300
    assert cut == "y" * 299 + "…"
    assert [line["outcome"] for line in logs.events("operation")] == [
        {"refusal": whole},
        {"refusal": cut},
    ]


async def test_a_read_counts_rows_whatever_the_result_holds(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def read(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"name": "SINV-0001", "docstatus": 0}

    error, _ = await call(monkeypatch, read)
    assert not error
    assert logs.events("operation")[0]["outcome"] == {"rows": 1}


async def test_the_operation_line_is_a_warning_only_for_a_refusal(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def read(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"records": []}

    async def refuse(inputs: Nothing, context: Context) -> dict[str, Any]:
        raise tools.Refusal("No.")

    assert not (await call(monkeypatch, read))[0]
    assert (await call(monkeypatch, refuse))[0]
    served, refused = logs.events("operation")
    assert (served["outcome"], served["level"]) == ({"rows": 0}, "info")
    assert (refused["outcome"], refused["level"]) == ({"refusal": "No."}, "warning")


async def test_a_create_names_the_document(monkeypatch: pytest.MonkeyPatch, logs: Logs) -> None:
    async def create(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"name": "SINV-0001", "warnings": []}

    error, _ = await call(monkeypatch, create, kind="create")
    assert not error
    assert logs.events("operation")[0]["outcome"] == {"document": "SINV-0001"}


async def test_a_write_too_large_without_its_tables_returns_its_number_and_comments(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    # REQ-001-PRS-NF003: the draft is written, whatever field takes its result over the limit
    async def create(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {
            "name": "SINV-0001",
            "modified": "2026-10-29 10:00:00.000000",
            "status": "Draft",
            "docstatus": 0,
            "company": "Example GmbH",
            "customer": "CUST-0001",
            "url": "https://erp.example.com/desk/sales-invoice/SINV-0001",
            "warnings": ["Possible duplicate of SINV-0000."],
            "truncated": ["items.description"],
            "outside_text": {"remarks": "x" * 200_000},
            "items": [{"item_code": "SKU-1"}],
        }

    erp = FakeErpnext()
    erp.fail(COMMENT_METHOD, 417, error(417, "ValidationError", "No comments"))
    error_, text = await call(monkeypatch, create, kind="create", erp=erp)
    assert not error_
    result = json.loads(text)
    # The fields every draft result has (REQ-001's Results), and the warnings, all of them
    assert set(result) == {
        "name",
        "modified",
        "status",
        "docstatus",
        "company",
        "url",
        "warnings",
        "truncated",
    }
    assert result["truncated"] == ["customer", "outside_text", "items"]
    duplicate, missing, note = result["warnings"]
    assert duplicate == "Possible duplicate of SINV-0000."
    assert "comment" in missing
    assert "customer, outside_text, items" in note
    assert logs.events("operation")[0]["outcome"] == {"document": "SINV-0001"}


def test_each_write_names_the_doctype_it_comments_on() -> None:
    writes = [op for op in tools.operations() if op.kind != "read"]
    assert writes
    assert all(op.doctype for op in writes)
    assert all(op.doctype is None for op in tools.operations() if op.kind == "read")


async def test_long_keys_and_lists_are_cut_in_the_line(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def read(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"records": []}

    arguments = {
        "k" * 10_000: list(range(10_000)),
        "nested": {str(i): i for i in range(10_000)},
        "texts": ["t" * 10_000, "u"],
    }
    error, text = await call(monkeypatch, read, arguments=arguments)
    assert error
    assert len(text) <= 300
    [operation] = logs.events("operation")
    logged = operation["arguments"]
    assert [len(key) for key in logged] == [200, 6, 5]
    assert logged["k" * 200] == list(range(100))
    assert logged["texts"] == ["t" * 200, "u"]
    assert len(logged["nested"]) == 100
    assert len(operation["outcome"]["refusal"]) <= 300


def test_an_updates_comment_and_its_change_check_take_the_same_keys() -> None:
    # REQ-001-PRS-F015: the comment names the given changes, the inputs DraftUpdate's own aren't
    assert tuple(drafts.DraftUpdate.model_fields) == tools.UPDATE_KEYS
