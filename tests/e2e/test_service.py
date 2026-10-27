"""The service end to end, against a fake JWKS: REQ-002-PRS-NF001 to
REQ-002-PRS-NF003, REQ-002-PRS-NF008 to REQ-002-PRS-NF012."""

import io
import json
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient

from erpel import log
from erpel.app import create_app
from erpel.config import Settings
from tests.fakes.jwks import FakeJwks, Signer, rsa_signer, token
from tests.fakes.settings import API_KEY, API_SECRET, ISSUER, RESOURCE_URL, settings

BASE = "https://erp.example.com"
METADATA = "/.well-known/oauth-protected-resource/mcp"
ACCEPT = {"accept": "application/json, text/event-stream"}
KNOWN_EVENTS = {"start", "operation", "rejection", "jwks", "error", "library"}


class Logs:
    def __init__(self) -> None:
        self.stream = io.StringIO()

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def events(self, name: str) -> list[dict[str, Any]]:
        return [line for line in self.lines() if line["event"] == name]


@pytest.fixture
def logs() -> Iterator[Logs]:
    captured = Logs()
    log.configure("DEBUG", captured.stream)
    yield captured
    lines = captured.lines()  # every line parses as JSON
    assert {line["event"] for line in lines} <= KNOWN_EVENTS
    text = captured.stream.getvalue()
    assert API_KEY not in text
    assert API_SECRET not in text


@pytest.fixture
def signer() -> Signer:
    return rsa_signer()


@pytest.fixture
def jwks(signer: Signer) -> FakeJwks:
    return FakeJwks([signer])


def client(jwks: FakeJwks, s: Settings | None = None) -> TestClient:
    return TestClient(create_app(s or settings(), jwks.client()), base_url=BASE)


def bearer(t: str) -> dict[str, str]:
    return {"authorization": f"Bearer {t}", **ACCEPT}


def initialize(c: TestClient, t: str, version: str) -> Any:
    return c.post(
        "/mcp",
        headers=bearer(t),
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
    )


def list_tools(c: TestClient, t: str, version: str) -> Any:
    params: dict[str, Any] = {}
    headers = {**bearer(t), "mcp-protocol-version": version}
    if version == "2026-07-28":
        headers["mcp-method"] = "tools/list"
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": version,
            "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "0"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }
    return c.post(
        "/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": params},
    )


@pytest.mark.parametrize("version", ["2025-06-18", "2025-11-25"])
def test_initialize_and_list_tools(
    jwks: FakeJwks, signer: Signer, logs: Logs, version: str
) -> None:
    t = token(signer)
    with client(jwks) as c:
        init = initialize(c, t, version)
        assert init.status_code == 200
        assert init.headers["content-type"].startswith("application/json")
        assert init.json()["result"]["protocolVersion"] == version
        tools = list_tools(c, t, version)
        assert tools.status_code == 200
        assert tools.json()["result"]["tools"] == []


def test_a_single_exchange_under_2026_07_28(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    with client(jwks) as c:
        response = list_tools(c, token(signer), "2026-07-28")
    assert response.status_code == 200
    assert response.json()["result"]["tools"] == []


def test_the_origin_header_changes_nothing(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    """REQ-002-PRS-NF004: no Origin check (ADR-002), the same answer for any client."""
    t = token(signer)
    answers: list[tuple[int, Any]] = []
    with client(jwks) as c:
        for origin in ["https://claude.ai", "https://attacker.example.net", "null", None]:
            headers = {**bearer(t), "mcp-protocol-version": "2025-11-25"}
            if origin is not None:
                headers["origin"] = origin
            response = c.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            answers.append((response.status_code, response.json()))
    assert answers == [(200, {"jsonrpc": "2.0", "id": 2, "result": {"tools": []}})] * 4


def test_no_session_state_between_processes(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    t = token(signer)
    with client(jwks) as first, client(jwks) as second:
        assert initialize(first, t, "2025-11-25").status_code == 200
        assert list_tools(second, t, "2025-11-25").status_code == 200


@pytest.mark.parametrize("method", ["GET", "DELETE", "OPTIONS", "PUT"])
def test_methods_other_than_post_get_405(jwks: FakeJwks, logs: Logs, method: str) -> None:
    with client(jwks) as c:
        response = c.request(method, "/mcp", headers={"authorization": "Bearer garbage"})
    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
    assert jwks.fetches == 0
    assert logs.events("rejection") == []


@pytest.mark.parametrize("path", ["/mcp/", "/mcp/x", "/", "/MCP", "/healthz/"])
def test_other_paths_are_404(jwks: FakeJwks, signer: Signer, logs: Logs, path: str) -> None:
    with client(jwks) as c:
        response = c.post(path, headers=bearer(token(signer)), json={}, follow_redirects=False)
    assert response.status_code == 404


def test_missing_token_gets_401_with_the_metadata_pointer(jwks: FakeJwks, logs: Logs) -> None:
    with client(jwks) as c:
        response = c.post("/mcp", headers=ACCEPT, json={})
    assert response.status_code == 401
    challenge = response.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")
    assert f'resource_metadata="{BASE}{METADATA}"' in challenge
    assert [(r["status"], r["reason"]) for r in logs.events("rejection")] == [
        (401, "no bearer token")
    ]


def test_metadata(jwks: FakeJwks, logs: Logs) -> None:
    with client(jwks) as c:
        response = c.get(METADATA, headers={"authorization": "Bearer garbage"})
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == RESOURCE_URL
    assert body["authorization_servers"] == [ISSUER]
    assert body["scopes_supported"] == ["openid"]
    assert body["bearer_methods_supported"] == ["header"]
    assert logs.events("rejection") == []


def test_metadata_is_served_during_a_jwks_outage(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    jwks.down = True
    with client(jwks) as c:
        response = c.get(METADATA, headers=bearer(token(signer)))
    assert response.status_code == 200
    assert response.json()["resource"] == RESOURCE_URL
    assert jwks.fetches == 0


def test_a_missing_scope_gets_403(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    s = settings(required_scopes="openid erpel")
    with client(jwks, s) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), json={})
        assert c.get(METADATA).json()["scopes_supported"] == ["openid", "erpel"]
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    assert [
        (r["status"], r["reason"], r["sub"], r["client"]) for r in logs.events("rejection")
    ] == [(403, "missing scope", "00000000-0000-0000-0000-000000000001", "erpel-agent")]


def test_a_refused_token_gets_401_and_one_short_line_each(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    person = token(signer, sub="11111111-1111-1111-1111-111111111111")
    with client(jwks) as c:
        statuses = {c.post("/mcp", headers=bearer(person), json={}).status_code for _ in range(50)}
    assert statuses == {401}
    lines = [line for line in logs.stream.getvalue().splitlines() if '"rejection"' in line]
    assert len(lines) == 50
    assert all(len(line) <= 300 for line in lines)
    first = logs.events("rejection")[0]
    assert first["reason"] == "wrong subject"
    assert first["sub"] == "11111111-1111-1111-1111-111111111111"
    assert first["client"] == "erpel-agent"


def test_rejection_lines_stay_short_whatever_the_claims(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    odd = '"\\\n\u0001' * 40
    with client(jwks) as c:
        c.post("/mcp", headers=bearer(token(signer, sub=odd, azp=odd, client_id="x")), json={})
    lines = [line for line in logs.stream.getvalue().splitlines() if '"rejection"' in line]
    assert len(lines) == 1
    assert len(lines[0]) <= 300


def test_a_2_mib_body_gets_413_before_the_token_check(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    with client(jwks) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413
    assert jwks.fetches == 0


def test_healthz_needs_nothing(jwks: FakeJwks, logs: Logs) -> None:
    jwks.down = True
    with client(jwks) as c:
        response = c.get("/healthz", headers={"authorization": "Bearer garbage"})
    assert response.status_code == 200
    assert jwks.fetches == 0
    assert logs.events("rejection") == []


def test_unreachable_jwks_gets_503_not_401(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    jwks.down = True
    with client(jwks) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), json={})
    assert response.status_code == 503
    assert response.headers["retry-after"] == "30"
    assert [(r["status"], r["reason"]) for r in logs.events("rejection")] == [
        (503, "no signing keys")
    ]
    assert logs.events("jwks")[0]["outcome"] == "failed"


def test_no_token_part_reaches_the_log_or_responses(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    tokens = [
        token(signer),
        token(signer, sub="someone-else"),
        token(rsa_signer("key-1"), sub="forged"),
        token(signer, exp=1),
    ]
    bodies: list[str] = []
    with client(jwks) as c:
        for t in tokens:
            response = c.post("/mcp", headers=bearer(t), json={})
            bodies.append(response.text + json.dumps(dict(response.headers)))
    text = logs.stream.getvalue() + "".join(bodies)
    for t in tokens:
        _, payload, signature = t.split(".")
        assert payload not in text
        assert signature not in text
