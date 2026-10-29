"""Running an operation: REQ-001-PRS-F008 (tool errors), REQ-002-PRS-NF008
(operation and error lines), with operations made up for the test."""

from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from enterich import tools
from enterich.erpnext import Erpnext
from enterich.shapes import Inputs
from enterich.tools import Context, Kind, Operation
from tests.conftest import Logs
from tests.fakes.erpnext import FakeErpnext
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
) -> tuple[bool, str]:
    op = Operation(
        name="try_it", title="Try it", description="A test.", kind=kind, inputs=Nothing, run=run
    )
    monkeypatch.setattr(tools, "operations", lambda: [op])
    s = settings(tools="try_it")
    [tool] = tools.build(s, Erpnext(s, FakeErpnext().transport()))
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


async def test_a_read_counts_rows_whatever_the_result_holds(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def read(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"name": "SINV-0001", "docstatus": 0}

    error, _ = await call(monkeypatch, read)
    assert not error
    assert logs.events("operation")[0]["outcome"] == {"rows": 1}


async def test_a_create_names_the_document(monkeypatch: pytest.MonkeyPatch, logs: Logs) -> None:
    async def create(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"name": "SINV-0001", "records": []}

    error, _ = await call(monkeypatch, create, kind="create")
    assert not error
    assert logs.events("operation")[0]["outcome"] == {"document": "SINV-0001"}


async def test_long_keys_and_lists_are_cut_in_the_line(
    monkeypatch: pytest.MonkeyPatch, logs: Logs
) -> None:
    async def read(inputs: Nothing, context: Context) -> dict[str, Any]:
        return {"records": []}

    arguments = {"k" * 10_000: list(range(10_000)), "nested": {str(i): i for i in range(10_000)}}
    error, text = await call(monkeypatch, read, arguments=arguments)
    assert error
    assert len(text) <= 300
    [operation] = logs.events("operation")
    logged = operation["arguments"]
    assert [len(key) for key in logged] == [200, 6]
    assert len(logged["k" * 200]) == 100
    assert len(logged["nested"]) == 100
    assert len(operation["outcome"]["refusal"]) <= 300
