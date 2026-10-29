"""The outer wrapper's own paths (ADR-002): errors, health checks, other protocols."""

import io
import json

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from enterich import log
from enterich.app import Wrapper


async def boom(request: Request) -> Response:
    raise RuntimeError("inner failure")


def wrapped() -> TestClient:
    # Starlette sends a 500 and re-raises, as the SDK's app does.
    inner = Starlette(routes=[Route("/mcp", boom, methods=["POST"])])
    return TestClient(Wrapper(inner, "/mcp"), raise_server_exceptions=False)


def test_an_unexpected_exception_is_logged_as_error_and_answered_500() -> None:
    stream = io.StringIO()
    log.configure("INFO", stream)
    response = wrapped().post("/mcp", json={})
    assert response.status_code == 500
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    errors = [line for line in lines if line["event"] == "error"]
    assert errors == [errors[0]]
    assert errors[0]["exception"] == "RuntimeError"
    assert errors[0]["message"] == "inner failure"


def test_the_error_line_carries_the_traceback_and_is_written_once() -> None:
    async def raw(scope: Scope, receive: Receive, send: Send) -> None:
        raise RuntimeError("raw failure")

    stream = io.StringIO()
    log.configure("INFO", stream)
    response = TestClient(Wrapper(raw, "/mcp"), raise_server_exceptions=False).post("/mcp", json={})
    assert response.status_code == 500
    assert response.json() == {"error": "internal error"}
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    lines = [line for line in lines if line.get("logger") != "httpx2"]  # the test client's own
    assert [line["event"] for line in lines] == ["error"]
    assert "raw failure" in lines[0]["traceback"]


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_healthz_allows_only_get_and_head(method: str) -> None:
    response = wrapped().request(method, "/healthz")
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD"


def test_websockets_are_closed() -> None:
    with pytest.raises(WebSocketDisconnect) as closed, wrapped().websocket_connect("/mcp"):
        pass
    assert closed.value.code == 1008
