"""Talking to Enterich as an MCP client would."""

import json
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from starlette.testclient import TestClient

from enterich.app import create_app
from enterich.config import Settings
from tests.conftest import Logs
from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import settings

BASE = "https://erp.example.com"
METADATA = "/.well-known/oauth-protected-resource/mcp"
ACCEPT = {"accept": "application/json, text/event-stream"}
VERSION = "2025-11-25"


def client(
    jwks: FakeJwks, s: Settings | None = None, erpnext: FakeErpnext | None = None
) -> TestClient:
    if erpnext is None:
        app = create_app(s or settings(), jwks.client())
    else:
        app = create_app(s or settings(), jwks.client(), erpnext_transport=erpnext.transport())
    return TestClient(app, base_url=BASE)


def bearer(t: str) -> dict[str, str]:
    return {"authorization": f"Bearer {t}", **ACCEPT}


@dataclass
class Result:
    error: bool
    text: str

    @property
    def data(self) -> Any:
        assert not self.error, self.text
        return json.loads(self.text)


class Session:
    """Stateless MCP calls with one token; the client never confirms anything
    (REQ-001-PRS-F013)."""

    def __init__(self, c: TestClient, token: str) -> None:
        self._c = c
        self._headers = {**bearer(token), "mcp-protocol-version": VERSION}
        self.answers: list[str] = []
        self.request_id = 0  # the last request's JSON-RPC ID; each request takes the next

    def _rpc(
        self, method: str, params: dict[str, Any], request_id: str | None = None
    ) -> dict[str, Any]:
        self.request_id += 1
        rpc_id = self.request_id if request_id is None else request_id
        response = self._c.post(
            "/mcp",
            headers=self._headers,
            json={"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params},
        )
        self.answers.append(response.text)
        assert response.status_code == 200, response.text
        return response.json()

    def tools(self) -> list[dict[str, Any]]:
        return self._rpc("tools/list", {})["result"]["tools"]

    def call(
        self, name: str, arguments: dict[str, Any] | None = None, request_id: str | None = None
    ) -> Result:
        """Call a tool, under the next request ID or under `request_id`."""
        answer = self._rpc("tools/call", {"name": name, "arguments": arguments or {}}, request_id)
        if "error" in answer:
            return Result(True, answer["error"]["message"])
        result = answer["result"]
        return Result(result["isError"], result["content"][0]["text"])


@contextmanager
def checked_session(
    c: TestClient, signer: Signer, logs: Logs, secrets: Iterable[str]
) -> Generator[Session]:
    """A client's session on `c` with a new token. Afterwards, neither the log nor any
    answer may carry one of `secrets` or a part of the token (REQ-002-PRS-NF010)."""
    t = token(signer)
    with c:
        session = Session(c, t)
        yield session
    seen = logs.stream.getvalue() + "".join(session.answers)
    _, payload, signature = t.split(".")
    for secret in (*secrets, payload, signature):
        assert secret not in seen
