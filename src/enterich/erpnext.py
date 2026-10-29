"""The one ERPNext client: the agent user's key, its limits, its refusals.

REQ-002-PRS-NF006 (one credential, the configured Host, no cookies, no
redirects, no proxy), REQ-002-PRS-NF011 (30 s per call, 10 MiB per answer)
and REQ-001-PRS-F008 (refusals reported as plain text).
"""

import html
import json
import re
import time
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any, cast
from urllib.parse import quote

import anyio
import httpx2

from enterich.config import Settings

CALL_TIMEOUT = 30.0
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_MESSAGE = 300
TAXES_METHOD = "erpnext.controllers.accounts_controller.get_taxes_and_charges"
COMMENT_METHOD = "frappe.desk.form.utils.add_comment"
# A tag starts with its name right after `<` or `</`; `qty < 0 and rate > 5` has none.
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")


class ErpnextError(Exception):
    """A call that ended without a usable answer; `str()` is the text for the agent."""


class Refused(ErpnextError):  # noqa: N818 - ERPNext's answer, not a fault of Enterich's
    """ERPNext answered with an error status."""

    def __init__(self, text: str, status: int, exc_type: str | None) -> None:
        super().__init__(text)
        self.status = status
        self.exc_type = exc_type


@dataclass
class Meter:
    calls: int = 0
    seconds: float = 0.0


_meter: ContextVar[Meter | None] = ContextVar("erpnext_meter", default=None)


@contextmanager
def metered() -> Generator[Meter]:
    """Count the ERPNext calls made inside the block and their total time."""
    meter = Meter()
    token = _meter.set(meter)
    try:
        yield meter
    finally:
        _meter.reset(token)


class Erpnext:
    def __init__(
        self, settings: Settings, transport: httpx2.AsyncBaseTransport | None = None
    ) -> None:
        key, secret = self._secrets = settings.secrets
        self._client = httpx2.AsyncClient(
            base_url=settings.erpnext_url,
            headers={
                "authorization": f"token {key}:{secret}",
                "host": settings.erpnext_host,
                "accept": "application/json",
            },
            # A jar that stores nothing: no session cookie ever goes back to ERPNext.
            cookies=CookieJar(policy=DefaultCookiePolicy(allowed_domains=[])),
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=None,  # CALL_TIMEOUT covers the whole call, body included
        )

    async def get_list(
        self,
        doctype: str,
        *,
        fields: Sequence[str],
        filters: Sequence[Sequence[Any]] = (),
        or_filters: Sequence[Sequence[Any]] = (),
        order_by: str,
        start: int,
        page_length: int,
    ) -> list[dict[str, Any]]:
        params = {
            "fields": json.dumps(list(fields)),
            "filters": json.dumps([list(f) for f in filters]),
            "order_by": order_by,
            "limit_start": str(start),
            "limit_page_length": str(page_length),
        }
        if or_filters:
            params["or_filters"] = json.dumps([list(f) for f in or_filters])
        answer = await self._call("GET", _resource(doctype), params)
        return cast("list[dict[str, Any]]", _expect(answer, "data", list))

    async def get_doc(self, doctype: str, name: str) -> dict[str, Any]:
        params = {"doctype": doctype, "name": name}
        answer = await self._call("GET", "/api/method/frappe.client.get", params)
        return cast("dict[str, Any]", _expect(answer, "message", dict))

    async def run_report(self, report: str, filters: dict[str, Any]) -> dict[str, Any]:
        params = {
            "report_name": report,
            "filters": json.dumps(filters),
            # A site's saved filters never replace Enterich's.
            "are_default_filters": "false",
        }
        answer = await self._call("GET", "/api/method/frappe.desk.query_report.run", params)
        message = cast("dict[str, Any]", _expect(answer, "message", dict))
        if not message.get("prepared_report"):
            _expect(message, "result", list)
        return message

    async def tax_rows(self, template_doctype: str, template: str) -> list[dict[str, Any]]:
        """A tax template's rows as ERPNext copies them into a document."""
        params = {"master_doctype": template_doctype, "master_name": template}
        answer = await self._call("GET", f"/api/method/{TAXES_METHOD}", params)
        rows = cast("list[Any]", _expect(answer, "message", list))
        if not all(isinstance(row, dict) for row in rows):
            raise ErpnextError("ERPNext's answer has tax rows that aren't records.")
        return cast("list[dict[str, Any]]", rows)

    async def insert(self, doctype: str, doc: dict[str, Any]) -> dict[str, Any]:
        """Insert a document; the answer is the document as saved."""
        answer = await self._call("POST", _resource(doctype), {}, doc)
        return cast("dict[str, Any]", _expect(answer, "data", dict))

    async def update(self, doctype: str, name: str, doc: dict[str, Any]) -> dict[str, Any]:
        """Save changes to a document; the answer is the document as saved."""
        path = f"{_resource(doctype)}/{quote(name, safe='')}"
        answer = await self._call("PUT", path, {}, doc)
        return cast("dict[str, Any]", _expect(answer, "data", dict))

    async def add_comment(self, doctype: str, name: str, content: str) -> None:
        # ERPNext takes the comment's author from the session; the two fields are ignored.
        body = {
            "reference_doctype": doctype,
            "reference_name": name,
            "content": content,
            "comment_email": "",
            "comment_by": "",
        }
        await self._call("POST", f"/api/method/{COMMENT_METHOD}", {}, body)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call(
        self, method: str, path: str, params: dict[str, str], body: dict[str, Any] | None = None
    ) -> Any:
        meter = _meter.get()
        started = time.monotonic()
        try:
            with anyio.fail_after(CALL_TIMEOUT):
                status, raw = await self._send(method, path, params, body)
        except TimeoutError:
            raise ErpnextError(f"ERPNext didn't answer within {CALL_TIMEOUT:g} seconds.") from None
        except httpx2.HTTPError as exc:
            raise ErpnextError(f"ERPNext can't be reached ({type(exc).__name__}).") from None
        finally:
            if meter is not None:
                meter.calls += 1
                meter.seconds += time.monotonic() - started
        if 300 <= status < 400:
            raise ErpnextError(
                f"ERPNext answered with a redirect ({status}); Enterich doesn't follow redirects. "
                "Check ENTERICH_ERPNEXT_URL."
            )
        try:
            answer = json.loads(raw) if raw else None
        except ValueError, RecursionError:
            answer = None
        if status >= 400:
            raise self._refusal(status, answer)
        if answer is None:
            raise ErpnextError("ERPNext's answer isn't JSON.")
        return answer

    async def _send(
        self, method: str, path: str, params: dict[str, str], body: dict[str, Any] | None
    ) -> tuple[int, bytes]:
        content = None if body is None else json.dumps(body, default=_number).encode()
        headers = {} if body is None else {"content-type": "application/json"}
        async with self._client.stream(
            method, path, params=params, content=content, headers=headers
        ) as response:
            received = bytearray()
            async for chunk in response.aiter_bytes():
                received += chunk
                if len(received) > MAX_RESPONSE_BYTES:
                    raise ErpnextError("ERPNext's answer exceeded 10 MiB.")
            return response.status_code, bytes(received)

    def _refusal(self, status: int, answer: Any) -> Refused:
        exc_type = answer.get("exc_type") if isinstance(answer, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        exc_type = exc_type if isinstance(exc_type, str) else None
        message = _first_message(answer)
        label = f"{status} {exc_type}" if exc_type else str(status)
        text = f"ERPNext refused the request ({label})."
        if message:
            text += f" ERPNext's message: {message}"
        for secret in self._secrets:
            text = text.replace(secret, "***")
        if len(text) > MAX_MESSAGE:
            text = text[: MAX_MESSAGE - 1] + "…"
        return Refused(text, status, exc_type)


def _resource(doctype: str) -> str:
    return f"/api/resource/{quote(doctype, safe='')}"


def _number(value: Decimal) -> float:
    """Decimal inputs go to ERPNext as JSON numbers; a body holds no other non-JSON type."""
    return float(value)


def _first_message(answer: Any) -> str | None:
    """The first of `_server_messages` as plain text; nothing else of the body."""
    if not isinstance(answer, dict):
        return None
    raw = answer.get("_server_messages")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    try:
        messages = json.loads(raw) if isinstance(raw, str) else None
        listed = cast("list[Any]", messages) if isinstance(messages, list) else []
        first = json.loads(listed[0]) if listed and isinstance(listed[0], str) else None
    except ValueError, RecursionError:
        return None
    message = first.get("message") if isinstance(first, dict) else first  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(message, str):
        return None
    return " ".join(html.unescape(_TAG.sub("", message)).split()) or None


def _expect[T](answer: Any, key: str, kind: type[T]) -> T:
    value = answer.get(key) if isinstance(answer, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(value, kind):
        raise ErpnextError(f"ERPNext's answer has no {key}.")
    return value
