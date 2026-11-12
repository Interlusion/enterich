"""The outer wrapper's own paths (ADR-002): errors, health checks, other protocols."""

import io
import json

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send
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


async def posted(
    messages: list[Message], headers: list[tuple[bytes, bytes]] | None = None
) -> tuple[list[bytes], list[int]]:
    """POST /mcp with these receive messages: the body the inner app read, the statuses sent."""
    read: list[bytes] = []
    statuses: list[int] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        read.append((await receive())["body"])

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        if message["type"] == "http.response.start":
            statuses.append(message["status"])

    scope: Scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": headers or []}
    await Wrapper(inner, "/mcp")(scope, receive, send)
    return read, statuses


@pytest.mark.anyio
async def test_a_client_gone_mid_body_hands_the_inner_app_what_arrived() -> None:
    read, _ = await posted(
        [
            {"type": "http.request", "body": b'{"a"', "more_body": True},
            {"type": "http.disconnect"},
        ]
    )
    assert read == [b'{"a"']


@pytest.mark.anyio
async def test_the_read_body_is_handed_out_once_and_then_receive_reaches_the_client() -> None:
    # REQ-002-PRS-NF011: the wrapper reads the body to count it; an inner app that waits
    # for http.disconnect afterwards must get it, not the body again.
    messages: list[Message] = [
        {"type": "http.request", "body": b"{}", "more_body": False},
        {"type": "http.disconnect"},
    ]
    received: list[Message] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        received.extend([await receive(), await receive()])

    async def receive() -> Message:
        return messages.pop(0)

    async def send(message: Message) -> None:
        pass

    scope: Scope = {"type": "http", "method": "POST", "path": "/mcp", "headers": []}
    await Wrapper(inner, "/mcp")(scope, receive, send)
    assert received == [
        {"type": "http.request", "body": b"{}", "more_body": False},
        {"type": "http.disconnect"},
    ]


@pytest.mark.anyio
async def test_a_body_in_several_parts_reaches_the_inner_app_whole() -> None:
    # Uvicorn splits a large body across messages; the last may carry no body key.
    read, _ = await posted(
        [
            {"type": "http.request", "body": b'{"a":', "more_body": True},
            {"type": "http.request", "body": b"1}", "more_body": True},
            {"type": "http.request", "more_body": False},
        ]
    )
    assert read == [b'{"a":1}']


@pytest.mark.anyio
async def test_parts_over_1_mib_together_get_413_without_a_content_length() -> None:
    # REQ-002-PRS-NF011: no part is over 1 MiB on its own.
    part = b"x" * (600 * 1024)
    read, statuses = await posted(
        [
            {"type": "http.request", "body": part, "more_body": True},
            {"type": "http.request", "body": part, "more_body": True},
            {"type": "http.request", "body": b"", "more_body": False},
        ]
    )
    assert (read, statuses) == ([], [413])


@pytest.mark.anyio
@pytest.mark.parametrize("declared", [b"2097152", b"abc"])
async def test_a_content_length_over_1_mib_or_not_a_number_gets_413_unread(
    declared: bytes,
) -> None:
    # REQ-002-PRS-NF011, kept cheap (REQ-002-URS-NF009): the body sent is small and stays unread.
    messages: list[Message] = [{"type": "http.request", "body": b"{}", "more_body": False}]
    read, statuses = await posted(messages, [(b"content-length", declared)])
    assert (read, statuses, len(messages)) == ([], [413], 1)


@pytest.mark.anyio
@pytest.mark.parametrize("declared", [True, False], ids=["content-length", "parts"])
@pytest.mark.parametrize("size", [1024 * 1024, 1024 * 1024 + 1], ids=["1-mib", "one-byte-more"])
async def test_exactly_1_mib_reaches_the_inner_app_and_one_byte_more_gets_413(
    declared: bool, size: int
) -> None:
    # REQ-002-PRS-NF011: only a body over 1 MiB is refused, whether declared or counted.
    half = size // 2
    messages: list[Message] = [
        {"type": "http.request", "body": b"x" * half, "more_body": True},
        {"type": "http.request", "body": b"x" * (size - half), "more_body": False},
    ]
    headers = [(b"content-length", str(size).encode())] if declared else None
    read, statuses = await posted(messages, headers)
    if size == 1024 * 1024:
        assert (read, statuses) == ([b"x" * size], [])
    else:
        assert (read, statuses) == ([], [413])


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_healthz_allows_only_get_and_head(method: str) -> None:
    response = wrapped().request(method, "/healthz")
    assert response.status_code == 405
    assert response.headers["allow"] == "GET, HEAD"


def test_healthz_answers_head_as_it_answers_get() -> None:
    # REQ-002-PRS-NF012: HEAD is in the Allow header above, so it gets the 200 that GET gets.
    assert wrapped().head("/healthz").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/healthz", 200),
        ("GET", "/nowhere", 404),
        ("GET", "/mcp", 405),
        ("POST", "/mcp", 413),
    ],
)
def test_the_wrappers_own_answers_are_json_with_their_length(
    method: str, path: str, status: int
) -> None:
    # REQ-002-PRS-NF012: uvicorn's h11 drops an answer whose content-length is not its length.
    body = b"x" * (1024 * 1024 + 1) if status == 413 else None
    response = wrapped().request(method, path, content=body)
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-length"] == str(len(response.content))


def test_websockets_are_closed() -> None:
    with pytest.raises(WebSocketDisconnect) as closed, wrapped().websocket_connect("/mcp"):
        pass
    assert closed.value.code == 1008
