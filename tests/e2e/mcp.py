"""Talking to Enterich as an MCP client would."""

import json
from dataclasses import dataclass
from typing import Any

from starlette.testclient import TestClient

from enterich.app import create_app
from enterich.config import Settings
from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks
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
    """Stateless MCP calls with one token; the client never confirms anything."""

    def __init__(self, c: TestClient, token: str) -> None:
        self._c = c
        self._headers = {**bearer(token), "mcp-protocol-version": VERSION}

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        response = self._c.post(
            "/mcp",
            headers=self._headers,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        assert response.status_code == 200, response.text
        return response.json()

    def tools(self) -> list[dict[str, Any]]:
        return self._rpc("tools/list", {})["result"]["tools"]

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Result:
        answer = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        if "error" in answer:
            return Result(True, answer["error"]["message"])
        result = answer["result"]
        return Result(result["isError"], result["content"][0]["text"])
