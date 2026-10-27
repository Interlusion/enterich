"""ASGI assembly: the SDK's MCP app inside Erpel's outer wrapper (ADR-002).

The wrapper serves only three paths: the MCP endpoint (POST only, at most
1 MiB), the protected resource metadata, and `/healthz`. It writes the
`rejection` log line from the response status of the MCP path, and answers
503 when no signing keys are available (ADR-003).
"""

import json
import logging
import traceback
from dataclasses import dataclass, field
from importlib.metadata import version

import httpx2
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from erpel import log
from erpel.auth import JWKS_RETRY_INTERVAL, JwksCache, KeysUnavailable, Verifier, last_refusal
from erpel.config import Settings

MAX_BODY = 1024 * 1024
RETRY_AFTER = str(int(JWKS_RETRY_INTERVAL))  # a retry before that finds no new keys
METADATA_PREFIX = "/.well-known/oauth-protected-resource"
MAX_LOGGED_ID = 64


def create_app(settings: Settings, jwks_client: httpx2.AsyncClient | None = None) -> ASGIApp:
    client = jwks_client or httpx2.AsyncClient(
        trust_env=False, timeout=10.0, follow_redirects=False
    )
    verifier = Verifier(settings, JwksCache(settings.jwks_url, client))
    server = MCPServer(
        name="erpel",
        version=version("erpel"),
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=settings.issuer,  # pyright: ignore[reportArgumentType] - pydantic parses the string
            resource_server_url=settings.resource_url,  # pyright: ignore[reportArgumentType]
            required_scopes=list(settings.required_scopes),
            # The verifier checks `aud` itself (ADR-003).
            validate_token_resource=False,
        ),
    )
    inner = server.streamable_http_app(
        streamable_http_path=settings.mcp_path,
        json_response=True,
        stateless_http=True,
        max_request_body_size=MAX_BODY,
        # No Origin check: every request needs a bearer token (ADR-002).
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        host=settings.host,
    )
    return Wrapper(inner, settings.mcp_path)


class Wrapper:
    def __init__(self, inner: ASGIApp, mcp_path: str) -> None:
        self._inner = inner
        self._mcp_path = mcp_path
        self._metadata_path = METADATA_PREFIX + mcp_path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._inner(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        path, method = scope["path"], scope["method"]
        if path == "/healthz":
            if method in ("GET", "HEAD"):
                await _respond(send, 200, {"status": "ok"})
            else:
                await _respond(
                    send, 405, {"error": "method not allowed"}, [(b"allow", b"GET, HEAD")]
                )
        elif path == self._metadata_path:
            # The metadata needs no token, and the SDK would check one on every path.
            headers = [(k, v) for k, v in scope["headers"] if k != b"authorization"]
            await self._inner({**scope, "headers": headers}, receive, send)
        elif path == self._mcp_path:
            await self._mcp(scope, receive, send)
        else:
            await _respond(send, 404, {"error": "not found"})

    async def _mcp(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["method"] != "POST":
            await _respond(send, 405, {"error": "method not allowed"}, [(b"allow", b"POST")])
            return
        body = await _read_body(scope, receive)
        if body is None:
            await _respond(send, 413, {"error": "request body over 1 MiB"})
            return

        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        response = _Response()

        async def watch(message: Message) -> None:
            # Starlette sends a 500 before re-raising an exception; hold it back,
            # so a KeysUnavailable from the verifier can become a 503 instead.
            if message["type"] == "http.response.start":
                response.status = message["status"]
            if response.status == 500:
                response.held.append(message)
            else:
                response.started = True
                await send(message)

        last_refusal.set(None)
        try:
            await self._inner(scope, replay, watch)
        except KeysUnavailable:
            _log_rejection(503, "no signing keys")
            await _respond(
                send,
                503,
                {"error": "temporarily_unavailable"},
                [(b"retry-after", RETRY_AFTER.encode())],
            )
            return
        except Exception as exc:  # noqa: BLE001 - logged once here, not again by uvicorn
            log.event(
                "error",
                logging.ERROR,
                exception=type(exc).__name__,
                message=str(exc)[:300],
                traceback=traceback.format_exc(),
            )
            if not response.held and not response.started:
                await _respond(send, 500, {"error": "internal error"})
        for message in response.held:
            await send(message)
        status = response.status
        if status == 401:
            refusal = last_refusal.get()
            if refusal is not None:
                _log_rejection(status, refusal.reason, refusal.subject, refusal.client)
            else:
                _log_rejection(status, "no bearer token")
        elif status == 403:
            # The token passed the check, so whose it is may be logged.
            user = scope.get("user")
            access = user.access_token if isinstance(user, AuthenticatedUser) else None
            subject = access.subject if access else None
            client = access.client_id if access else None
            _log_rejection(status, "missing scope", subject, client)


@dataclass
class _Response:
    status: int = 0
    started: bool = False
    held: list[Message] = field(default_factory=list[Message])


async def _read_body(scope: Scope, receive: Receive) -> bytes | None:
    """The whole request body, or None when it exceeds MAX_BODY."""
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                if int(value) > MAX_BODY:
                    return None
            except ValueError:
                return None
    body = bytearray()
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return bytes(body)
        body += message.get("body", b"")
        if len(body) > MAX_BODY:
            return None
        if not message.get("more_body", False):
            return bytes(body)


def _log_rejection(
    status: int, reason: str, subject: str | None = None, client: str | None = None
) -> None:
    fields: dict[str, object] = {"status": status, "reason": reason}
    if subject is not None:
        fields["sub"] = _fit(subject)
    if client is not None:
        fields["client"] = _fit(client)
    log.event("rejection", logging.WARNING, **fields)


def _fit(value: str) -> str:
    """Cut so that the JSON-encoded value stays within MAX_LOGGED_ID characters."""
    while len(json.dumps(value, ensure_ascii=False)) - 2 > MAX_LOGGED_ID:
        value = value[:-1]
    return value


async def _respond(
    send: Send, status: int, body: dict[str, str], headers: list[tuple[bytes, bytes]] | None = None
) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                *(headers or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
