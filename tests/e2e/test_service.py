"""The service end to end, against a fake JWKS: REQ-002-PRS-NF001, REQ-002-PRS-NF002,
REQ-002-PRS-NF003, REQ-002-PRS-NF008, REQ-002-PRS-NF009, REQ-002-PRS-NF010,
REQ-002-PRS-NF011, REQ-002-PRS-NF012."""

import json
from typing import Any

import httpx2
import pytest
from starlette.testclient import TestClient

from enterich.app import create_app
from enterich.tools import names
from tests.conftest import Logs
from tests.e2e.mcp import ACCEPT, BASE, METADATA, bearer, client
from tests.fakes.jwks import FakeJwks, Signer, rsa_signer, token
from tests.fakes.settings import ISSUER, RESOURCE_URL, settings


def offered(answer: Any) -> list[str]:
    return sorted(tool["name"] for tool in answer["result"]["tools"])


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
        assert offered(tools.json()) == list(names())


def test_a_single_exchange_under_2026_07_28(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    with client(jwks) as c:
        response = list_tools(c, token(signer), "2026-07-28")
    assert response.status_code == 200
    assert offered(response.json()) == list(names())


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
    assert [status for status, _ in answers] == [200] * 4
    assert all(answer == answers[0][1] for _, answer in answers)
    assert offered(answers[0][1]) == list(names())


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
    s = settings(required_scopes="openid enterich")
    with client(jwks, s) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), json={})
        assert c.get(METADATA).json()["scopes_supported"] == ["openid", "enterich"]
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    assert [
        (r["status"], r["reason"], r["sub"], r["client"]) for r in logs.events("rejection")
    ] == [(403, "missing scope", "00000000-0000-0000-0000-000000000001", "enterich-agent")]


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
    assert first["client"] == "enterich-agent"


def test_rejection_lines_stay_short_whatever_the_claims(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    odd = '"\\\n\u0001' * 40
    with client(jwks) as c:
        c.post("/mcp", headers=bearer(token(signer, sub=odd, azp=odd, client_id="x")), json={})
    lines = [line for line in logs.stream.getvalue().splitlines() if '"rejection"' in line]
    assert len(lines) == 1
    assert len(lines[0]) <= 300


def test_a_kid_with_a_newline_forges_no_log_line(jwks: FakeJwks, logs: Logs) -> None:
    # Written raw into the log, this kid would start a line of its own.
    forger = rsa_signer('x"\n{"event": "start", "sub": "forged"}', key=1)
    with client(jwks) as c:
        response = c.post("/mcp", headers=bearer(token(forger)), json={})
    assert response.status_code == 401
    lines = logs.lines()  # each line is one JSON object, or this fails
    assert [line for line in lines if line.get("sub") == "forged"] == []
    assert [r["reason"] for r in logs.events("rejection")] == ["unknown key"]


def test_a_2_mib_body_gets_413_before_the_token_check(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    with client(jwks) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413
    assert jwks.fetches == 0


def test_shutdown_closes_the_outgoing_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[httpx2.AsyncClient] = []

    class Recorded(httpx2.AsyncClient):
        async def aclose(self) -> None:
            closed.append(self)
            await super().aclose()

    monkeypatch.setattr(httpx2, "AsyncClient", Recorded)
    with TestClient(create_app(settings()), base_url=BASE):
        assert closed == []
    assert len(closed) == 2  # the JWKS client and the ERPNext client


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
        token(rsa_signer("key-1", key=1), sub="forged"),
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
