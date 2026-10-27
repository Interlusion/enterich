"""A fake ERPNext v16 REST API: records every request, answers from memory."""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

import anyio
import httpx2

COMPANY = "Example GmbH"


@dataclass
class Received:
    method: str
    path: str
    params: dict[str, Any]
    headers: dict[str, str]
    body: Any

    def param(self, name: str) -> Any:
        """A query parameter, JSON-decoded where ERPNext expects JSON."""
        value = self.params.get(name)
        if isinstance(value, str) and value[:1] in "[{":
            return json.loads(value)
        return value


@dataclass
class FakeErpnext:
    docs: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict[str, dict[str, dict[str, Any]]]
    )
    received: list[Received] = field(default_factory=list[Received])
    # path -> (status, JSON body): the next request to that path gets it
    failures: dict[str, tuple[int, Any]] = field(default_factory=dict[str, tuple[int, Any]])
    delay: float = 0.0
    set_cookie: bool = False
    redirect: bool = False
    huge_response: bool = False
    raw: tuple[int, bytes] | None = None  # (status, body) for every request

    def add(self, doctype: str, doc: dict[str, Any]) -> dict[str, Any]:
        self.docs.setdefault(doctype, {})[doc["name"]] = doc
        return doc

    def fail(self, path: str, status: int, body: Any) -> None:
        self.failures[path] = (status, body)

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self.handle)

    async def handle(self, request: httpx2.Request) -> httpx2.Response:
        params = dict(request.url.params.multi_items())
        body = json.loads(request.content) if request.content else None
        self.received.append(
            Received(request.method, request.url.path, params, dict(request.headers), body)
        )
        if self.delay:
            await anyio.sleep(self.delay)
        headers = {"set-cookie": "sid=abc; Path=/"} if self.set_cookie else {}
        if self.redirect:
            return httpx2.Response(302, headers={"location": "https://elsewhere.example.net/"})
        if self.raw is not None:
            return httpx2.Response(self.raw[0], content=self.raw[1])
        if self.huge_response:
            return httpx2.Response(200, content=b'{"data": "' + b"x" * (20 * 1024 * 1024) + b'"}')
        if request.url.path in self.failures:
            status, failure = self.failures.pop(request.url.path)
            return httpx2.Response(status, json=failure, headers=headers)
        if request.url.path.startswith("/api/resource/") and request.method == "GET":
            doctype = unquote(request.url.path.removeprefix("/api/resource/"))
            return httpx2.Response(200, json={"data": self._list(doctype, params)}, headers=headers)
        if request.url.path == "/api/method/frappe.client.get":
            doc = self.docs.get(params.get("doctype", ""), {}).get(params.get("name", ""))
            if doc is None:
                return httpx2.Response(404, json=error(404, "DoesNotExistError", "Not found"))
            return httpx2.Response(200, json={"message": doc}, headers=headers)
        return httpx2.Response(404, json=error(404, "DoesNotExistError", "No such route"))

    def _list(self, doctype: str, params: dict[str, str]) -> list[dict[str, Any]]:
        docs = list(self.docs.get(doctype, {}).values())
        filters = json.loads(params.get("filters", "[]"))
        or_filters = json.loads(params.get("or_filters", "[]"))
        docs = [d for d in docs if all(_matches(d, f) for f in filters)]
        if or_filters:
            docs = [d for d in docs if any(_matches(d, f) for f in or_filters)]
        order = params.get("order_by", "name asc").split()
        docs.sort(key=lambda d: str(d.get(order[0], "")), reverse=order[-1] == "desc")
        start = int(params.get("limit_start", 0))
        length = int(params.get("limit_page_length", 20))
        fields = json.loads(params.get("fields", '["name"]'))
        return [{f: d.get(f) for f in fields} for d in docs[start : start + length]]


def _matches(doc: dict[str, Any], condition: list[Any]) -> bool:
    name, op, value = condition
    actual = doc.get(name)
    match op:
        case "=":
            return actual == value
        case "!=":
            return actual != value
        case "in":
            return actual in value
        case "like":
            return _like(str(value)).fullmatch(str(actual or "")) is not None
        case ">":
            return actual is not None and actual > value
        case "<":
            return actual is not None and actual < value
        case _:
            raise AssertionError(f"filter operator the fake doesn't know: {op}")


def _like(pattern: str) -> re.Pattern[str]:
    """SQL LIKE with backslash escapes, case-insensitive, as MariaDB does it."""
    out: list[str] = []
    chars = iter(pattern)
    for char in chars:
        if char == "\\":
            out.append(re.escape(next(chars, "\\")))
        elif char == "%":
            out.append(".*")
        elif char == "_":
            out.append(".")
        else:
            out.append(re.escape(char))
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def error(status: int, exc_type: str, message: str, traceback: str | None = None) -> dict[str, Any]:
    """An error body as Frappe sends it."""
    return {
        "exc_type": exc_type,
        "exception": f"frappe.exceptions.{exc_type}: {message}",
        "exc": json.dumps([traceback or f"Traceback (most recent call last):\n  ... {exc_type}"]),
        "_server_messages": json.dumps(
            [json.dumps({"message": message, "title": "Message", "indicator": "red"})]
        ),
    }


def item(code: str = "SKU-1", **overrides: Any) -> dict[str, Any]:
    """An Item as frappe.client.get returns it."""
    doc: dict[str, Any] = {
        "doctype": "Item",
        "name": code,
        "item_code": code,
        "item_name": f"Widget {code}",
        "item_group": "Products",
        "stock_uom": "Nos",
        "is_stock_item": 1,
        "disabled": 0,
        "description": f"<p>The widget {code}</p>",
        "modified": "2026-10-20 10:00:00.000000",
        "owner": "Administrator",
        "item_defaults": [
            {
                "doctype": "Item Default",
                "company": "Other AG",
                "income_account": "4000 - Sales - OT",
                "expense_account": "5000 - Cost - OT",
                "selling_cost_center": "Main - OT",
                "buying_cost_center": "Main - OT",
            },
            {
                "doctype": "Item Default",
                "company": COMPANY,
                "income_account": "4000 - Sales - EX",
                "expense_account": "5000 - Cost - EX",
                "selling_cost_center": "Main - EX",
                "buying_cost_center": "Purchasing - EX",
            },
        ],
        "taxes": [
            {
                "doctype": "Item Tax",
                "item_tax_template": "VAT 7% - EX",
                "tax_category": "Reduced",
                "valid_from": "2026-01-01",
            }
        ],
    }
    doc.update(overrides)
    return doc
