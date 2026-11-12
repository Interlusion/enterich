"""The service as a whole, against a fake JWKS: REQ-002-PRS-NF001, REQ-002-PRS-NF002,
REQ-002-PRS-NF003, REQ-002-PRS-NF008, REQ-002-PRS-NF009, REQ-002-PRS-NF010,
REQ-002-PRS-NF011, REQ-002-PRS-NF012."""

import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version as installed
from typing import Any

import httpx2
import pytest
from starlette.testclient import TestClient

from enterich.app import create_app
from enterich.auth import Verifier
from enterich.tools import names
from tests.conftest import Logs
from tests.fakes.jwks import FakeJwks, Signer, rsa_signer, token
from tests.fakes.settings import API_KEY, API_SECRET, ISSUER, RESOURCE_URL, settings
from tests.integration.mcp import ACCEPT, BASE, METADATA, bearer, client


def offered(answer: Any) -> list[str]:
    return sorted(tool["name"] for tool in answer["result"]["tools"])


def initialize(c: TestClient, t: str, version: str, path: str = "/mcp") -> Any:
    return c.post(
        path,
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


def list_tools(c: TestClient, t: str, version: str, path: str = "/mcp") -> Any:
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
        path,
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
        server = init.json()["result"]["serverInfo"]
        assert (server["name"], server["version"]) == ("enterich", installed("enterich"))
        tools = list_tools(c, t, version)
        assert tools.status_code == 200
        assert offered(tools.json()) == list(names())


def test_a_single_exchange_under_2026_07_28(jwks: FakeJwks, signer: Signer, logs: Logs) -> None:
    with client(jwks) as c:
        response = list_tools(c, token(signer), "2026-07-28")
    assert response.status_code == 200
    assert offered(response.json()) == list(names())


@pytest.mark.parametrize("host", ["0.0.0.0", "127.0.0.1"])
def test_the_origin_header_changes_nothing(
    jwks: FakeJwks, signer: Signer, logs: Logs, host: str
) -> None:
    """REQ-002-PRS-NF004: no Origin check (ADR-002), the same answer for any client, also
    when Enterich listens on a loopback address."""
    t = token(signer)
    answers: list[tuple[int, str]] = []
    with client(jwks, settings(host=host)) as c:
        for origin in ["https://claude.ai", "https://attacker.example.net", "null", None]:
            headers = {**bearer(t), "mcp-protocol-version": "2025-11-25"}
            if origin is not None:
                headers["origin"] = origin
            response = c.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            answers.append((response.status_code, response.text))
    assert [status for status, _ in answers] == [200] * 4
    bodies = [json.loads(text) for _, text in answers]
    assert all(body == bodies[0] for body in bodies)
    assert offered(bodies[0]) == list(names())


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


def test_mcp_is_served_at_the_path_of_the_resource_url(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    resource = "https://mcp.example.com/erp/agent"
    t = token(signer, aud=[resource])
    with client(jwks, settings(resource_url=resource)) as c:
        assert initialize(c, t, "2025-11-25", "/erp/agent").status_code == 200
        tools = list_tools(c, t, "2025-11-25", "/erp/agent")
        assert tools.status_code == 200
        assert offered(tools.json()) == list(names())
        metadata = c.get("/.well-known/oauth-protected-resource/erp/agent")
        assert metadata.status_code == 200
        assert metadata.json()["resource"] == resource
        assert c.post("/mcp", headers=bearer(t), json={}).status_code == 404
        assert c.get(METADATA).status_code == 404


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


def test_a_long_subject_and_client_are_cut_to_64_characters(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    subject, client_id = "s" * 64 + "!", "c" * 64 + "!"
    with client(jwks) as c:
        c.post("/mcp", headers=bearer(token(signer, sub=subject, azp=client_id)), json={})
    assert [
        (r["status"], r["reason"], r["sub"], r["client"]) for r in logs.events("rejection")
    ] == [(401, "wrong client", "s" * 64, "c" * 64)]


def test_rejection_lines_stay_short_with_non_ascii_claims(
    jwks: FakeJwks, signer: Signer, logs: Logs
) -> None:
    # Cut by characters, the values stay short only if the line keeps them unescaped.
    with client(jwks) as c:
        c.post("/mcp", headers=bearer(token(signer, sub="ä" * 200, azp="€" * 200)), json={})
    lines = [line for line in logs.stream.getvalue().splitlines() if '"rejection"' in line]
    assert len(lines) == 1
    assert len(lines[0]) <= 300
    assert '"sub": "ää' in lines[0]
    assert '"client": "€€' in lines[0]


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


def test_shutdown_leaves_a_handed_in_jwks_client_open(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[httpx2.AsyncClient] = []

    class Recorded(httpx2.AsyncClient):
        async def aclose(self) -> None:
            closed.append(self)
            await super().aclose()

    monkeypatch.setattr(httpx2, "AsyncClient", Recorded)
    handed_in = Recorded()
    with TestClient(create_app(settings(), handed_in), base_url=BASE):
        assert closed == []
    assert len(closed) == 1  # the ERPNext client; the caller closes its own
    assert handed_in not in closed
    assert not handed_in.is_closed


@dataclass
class LocalJwks:
    """A JWKS on loopback over real HTTP, for the client create_app builds itself."""

    url: str
    redirect: bool = False  # answer with a redirect to /moved, which serves the keys
    paths: list[str] = field(default_factory=list[str])


@pytest.fixture
def local_jwks(jwks: FakeJwks) -> Iterator[LocalJwks]:
    keys = json.dumps({"keys": [s.jwk() for s in jwks.signers]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            served.paths.append(self.path)
            if served.redirect and self.path == "/certs":
                self.send_response(302)
                self.send_header("location", "/moved")
                self.send_header("content-length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(keys)))
            self.end_headers()
            self.wfile.write(keys)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    served = LocalJwks(f"http://127.0.0.1:{server.server_address[1]}/certs")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield served
    server.shutdown()
    server.server_close()


def test_the_jwks_client_follows_no_redirect(
    local_jwks: LocalJwks, signer: Signer, logs: Logs
) -> None:
    """REQ-002-PRS-NF001: keys come from the configured JWKS URL and no other source."""
    local_jwks.redirect = True
    with TestClient(create_app(settings(jwks_url=local_jwks.url)), base_url=BASE) as c:
        response = initialize(c, token(signer), "2025-11-25")
    assert response.status_code == 503
    assert local_jwks.paths == ["/certs"]


def test_the_jwks_client_takes_no_proxy_from_the_environment(
    local_jwks: LocalJwks, signer: Signer, logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(name, "http://127.0.0.1:9")  # nothing listens there
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    with TestClient(create_app(settings(jwks_url=local_jwks.url)), base_url=BASE) as c:
        response = initialize(c, token(signer), "2025-11-25")
    assert response.status_code == 200
    assert local_jwks.paths == ["/certs"]


def test_a_jwks_fetch_has_a_time_limit(
    local_jwks: LocalJwks, signer: Signer, logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    limits: list[dict[str, float | None]] = []
    send = httpx2.AsyncClient.send

    async def recorded(
        self: httpx2.AsyncClient, request: httpx2.Request, **kwargs: Any
    ) -> httpx2.Response:
        limits.append(request.extensions["timeout"])
        return await send(self, request, **kwargs)

    monkeypatch.setattr(httpx2.AsyncClient, "send", recorded)
    with TestClient(create_app(settings(jwks_url=local_jwks.url)), base_url=BASE) as c:
        response = initialize(c, token(signer), "2025-11-25")
    assert response.status_code == 200
    assert len(limits) == 1
    assert None not in limits[0].values()


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


def test_an_exception_in_the_mcp_app_is_logged_without_the_api_key_and_secret(
    jwks: FakeJwks, signer: Signer, logs: Logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def failing(self: Verifier, t: str) -> None:
        raise RuntimeError(f"key {API_KEY} secret {API_SECRET}")

    monkeypatch.setattr(Verifier, "verify_token", failing)
    with client(jwks) as c:
        response = c.post("/mcp", headers=bearer(token(signer)), json={})
    assert response.status_code == 500
    assert API_KEY not in response.text
    assert API_SECRET not in response.text
    [line] = logs.events("error")
    assert line["exception"] == "RuntimeError"
    assert line["message"] == "key *** secret ***"
    assert "key *** secret ***" in line["traceback"]
    assert API_KEY not in line["traceback"]
    assert API_SECRET not in line["traceback"]
