"""A fake ERPNext v16 REST API: records every request, answers from memory."""

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, cast
from urllib.parse import unquote

import anyio
import httpx2

COMPANY = "Example GmbH"

# The v16 fields the fake lets a list select or filter on, checked against the
# DocType JSON of ERPNext 16.52 and Frappe 16.54; ERPNext refuses any other.
STANDARD_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx"}
FIELDS: dict[str, set[str]] = {
    "Item": {
        "item_code",
        "item_name",
        "item_group",
        "stock_uom",
        "is_stock_item",
        "disabled",
        "description",
    },
    "Customer": {
        "customer_name",
        "customer_type",
        "customer_group",
        "tax_id",
        "default_currency",
        "disabled",
        "payment_terms",
    },
    "Address": {
        "address_type",
        "is_primary_address",
        "address_line1",
        "address_line2",
        "city",
        "pincode",
        "country",
    },
    "Sales Invoice": {
        "company",
        "customer",
        "customer_name",
        "posting_date",
        "due_date",
        "currency",
        "net_total",
        "grand_total",
        "outstanding_amount",
        "status",
        "is_return",
        "taxes_and_charges",
        "total_taxes_and_charges",
        "return_against",
        "remarks",
    },
    "Sales Invoice Item": {
        "item_code",
        "item_name",
        "description",
        "qty",
        "uom",
        "rate",
        "amount",
        "income_account",
        "item_tax_template",
        "cost_center",
        "is_free_item",
    },
    "Sales Taxes and Charges Template": {
        "title",
        "is_default",
        "tax_category",
        "disabled",
        "company",
    },
    "Dynamic Link": {"link_doctype", "link_name"},
}
# DocType -> {table field: child DocType}
TABLES: dict[str, dict[str, str]] = {
    "Item": {"item_defaults": "Item Default", "taxes": "Item Tax"},
    "Address": {"links": "Dynamic Link"},
    "Sales Invoice": {"items": "Sales Invoice Item", "taxes": "Sales Taxes and Charges"},
    "Sales Taxes and Charges Template": {"taxes": "Sales Taxes and Charges"},
}


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
    # report name -> rows, as the report's execute() returns them
    reports: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict[str, list[dict[str, Any]]]
    )
    prepared: set[str] = field(default_factory=set[str])
    # The site's today, which a draft without set_posting_time gets at every save
    today: str = "2026-10-29"
    # item code -> price list rate
    prices: dict[str, float] = field(default_factory=dict[str, float])
    # item code -> the rate a price pricing rule sets
    rules: dict[str, float] = field(default_factory=dict[str, float])
    # item code -> the free item a product pricing rule adds
    free_items: dict[str, str] = field(default_factory=dict[str, str])
    comments: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    saves: int = 0

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
        if request.url.path.startswith("/api/resource/"):
            # One segment per DocType and name, each percent-decoded on its own
            raw = request.url.raw_path.decode().partition("?")[0]
            doctype, *rest = [unquote(s) for s in raw.removeprefix("/api/resource/").split("/")]
            if request.method == "GET" and not rest:
                if problem := _unknown_field(doctype, params):
                    return httpx2.Response(417, json=error(417, "DataError", problem))
                data = self._list(doctype, params)
                return httpx2.Response(200, json={"data": data}, headers=headers)
            if request.method == "POST" and not rest:
                return self._insert(doctype, cast("dict[str, Any]", body))
            if request.method == "PUT" and len(rest) == 1:
                return self._update(doctype, rest[0], cast("dict[str, Any]", body))
        if request.url.path == TAXES_METHOD and request.method == "GET":
            template = self.docs.get(params["master_doctype"], {}).get(params["master_name"])
            if template is None:
                return httpx2.Response(404, json=error(404, "DoesNotExistError", "Not found"))
            rows = [{k: v for k, v in r.items() if k != "doctype"} for r in template["taxes"]]
            return httpx2.Response(200, json={"message": rows})
        if request.url.path == COMMENT_METHOD and request.method in ("POST", "PUT"):
            comment = cast("dict[str, Any]", body)
            self.comments.append(comment)
            return httpx2.Response(200, json={"message": {"name": "c1", **comment}})
        if request.url.path == "/api/method/frappe.desk.query_report.run":
            return httpx2.Response(200, json={"message": self._report(params)}, headers=headers)
        if request.url.path == "/api/method/frappe.client.get":
            doc = self.docs.get(params.get("doctype", ""), {}).get(params.get("name", ""))
            if doc is None:
                return httpx2.Response(404, json=error(404, "DoesNotExistError", "Not found"))
            return httpx2.Response(200, json={"message": doc}, headers=headers)
        return httpx2.Response(404, json=error(404, "DoesNotExistError", "No such route"))

    def _insert(self, doctype: str, body: dict[str, Any]) -> httpx2.Response:
        name = f"ACC-SINV-2026-{101 + len(self.docs.get(doctype, {})):05d}"
        doc = {"doctype": doctype, "name": name, "owner": "agent@example.com", **body}
        return self._save(doctype, copy.deepcopy(doc))

    def _update(self, doctype: str, name: str, body: dict[str, Any]) -> httpx2.Response:
        stored = self.docs.get(doctype, {}).get(name)
        if stored is None:
            return httpx2.Response(404, json=error(404, "DoesNotExistError", "Not found"))
        if _timestamp(body.get("modified")) != _timestamp(stored["modified"]):
            message = (
                f"Error: Document has been modified after you have opened it "
                f"({stored['modified']}, {body.get('modified')}). "
                "Please refresh to get the latest document."
            )
            return httpx2.Response(417, json=error(417, "TimestampMismatchError", message))
        if stored["docstatus"] != 0:
            message = "Not allowed to change fields after submission"
            return httpx2.Response(417, json=error(417, "UpdateAfterSubmitError", message))
        doc = copy.deepcopy(stored)
        doc.update({k: copy.deepcopy(v) for k, v in body.items() if k != "modified"})
        return self._save(doctype, doc)

    def _save(self, doctype: str, doc: dict[str, Any]) -> httpx2.Response:
        """Save a sales invoice draft as v16 does: posting date, prices, pricing rules, totals."""
        party = self.docs.get("Customer", {}).get(doc.get("customer", ""))
        if party is None:
            message = f"Could not find Customer: {doc.get('customer')}"
            return httpx2.Response(417, json=error(417, "LinkValidationError", message))
        if not doc.get("set_posting_time"):
            doc["posting_date"] = self.today
        if not doc.get("due_date"):
            doc["due_date"] = str(date.fromisoformat(doc["posting_date"]) + timedelta(days=30))
        rows = [r for r in _rows(doc, "items") if not r.get("is_free_item")]
        for row in rows:
            code = row["item_code"]
            rate = self.rules.get(code, row.get("rate") or self.prices.get(code, 0.0))
            # Rounded to the field's precision: the site's float precision, the currency's
            row.update(qty=round(row["qty"], 3), rate=round(rate, 2), is_free_item=0)
            row["pricing_rules"] = '[\n "PRLE-0001"\n]' if code in self.rules else ""
        for code in [r["item_code"] for r in rows if r["item_code"] in self.free_items]:
            rows.append(
                {"item_code": self.free_items[code], "qty": 1, "rate": 0.0, "is_free_item": 1}
            )
        for row in rows:
            row.update(doctype="Sales Invoice Item", amount=round(row["qty"] * row["rate"], 2))
            row.setdefault("uom", "Nos")
        net_total = round(sum(r["amount"] for r in rows), 2)
        taxes = _rows(doc, "taxes")
        for tax in taxes:
            tax["tax_amount"] = round(net_total * tax["rate"] / 100, 2)
        total_taxes = round(sum(t["tax_amount"] for t in taxes), 2)
        self.saves += 1
        doc.update(
            items=rows,
            taxes=taxes,
            customer_name=party["customer_name"],
            currency="EUR",
            net_total=net_total,
            total_taxes_and_charges=total_taxes,
            grand_total=round(net_total + total_taxes, 2),
            outstanding_amount=round(net_total + total_taxes, 2),
            status="Draft",
            docstatus=0,
            modified=f"2026-10-28 12:00:00.{self.saves:06d}",
        )
        self.add(doctype, doc)
        return httpx2.Response(200, json={"data": doc})

    def _list(self, doctype: str, params: dict[str, str]) -> list[dict[str, Any]]:
        docs = list(self.docs.get(doctype, {}).values())
        filters = json.loads(params.get("filters", "[]"))
        or_filters = json.loads(params.get("or_filters", "[]"))
        docs = [d for d in docs if _matches_all(doctype, d, filters)]
        if or_filters:
            docs = [d for d in docs if any(_matches(d, f) for f in or_filters)]
        order = params.get("order_by", "name asc").split()
        docs.sort(key=lambda d: str(d.get(order[0], "")), reverse=order[-1] == "desc")
        start = int(params.get("limit_start", 0))
        length = int(params.get("limit_page_length", 20))
        fields: list[str] = json.loads(params.get("fields", '["name"]'))
        tables = {f.partition(".")[0] for f in fields if "." in f}
        if not tables:
            return [{f: d.get(f) for f in fields} for d in docs[start : start + length]]
        # A child field joins its table: one row per child row, the field under its own name
        [table] = tables
        joined: list[dict[str, Any]] = []
        for doc in docs:
            for row in cast("list[dict[str, Any]]", doc.get(table) or [{}]):
                joined.append(
                    {
                        f.rpartition(".")[2]: (row if "." in f else doc).get(f.rpartition(".")[2])
                        for f in fields
                    }
                )
        return joined[start : start + length]

    def _report(self, params: dict[str, str]) -> dict[str, Any]:
        name = params["report_name"]
        if name in self.prepared:
            return {"prepared_report": True, "doc": None}
        rows = [dict(row) for row in self.reports.get(name, [])]
        total = ["Total"] + [""] * 5  # Frappe appends the total row as a list
        return {"result": [*rows, total] if rows else rows, "columns": [], "add_total_row": 1}


def _timestamp(value: Any) -> datetime | None:
    """`modified` as `check_if_latest` compares it: parsed, not as text."""
    try:
        return datetime.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _rows(doc: dict[str, Any], table: str) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", doc.get(table) or [])


TAXES_METHOD = "/api/method/erpnext.controllers.accounts_controller.get_taxes_and_charges"
COMMENT_METHOD = "/api/method/frappe.desk.form.utils.add_comment"


def _unknown_field(doctype: str, params: dict[str, str]) -> str | None:
    """What v16 would refuse in a list call: a field or child table the DocType lacks."""
    known = FIELDS.get(doctype, set()) | STANDARD_FIELDS
    tables = TABLES.get(doctype, {})
    conditions = json.loads(params.get("filters", "[]")) + json.loads(
        params.get("or_filters", "[]")
    )
    for selected in json.loads(params.get("fields", '["name"]')):
        table, _, field = selected.rpartition(".")
        child = tables.get(table)
        if (child is None and table) or field not in (FIELDS.get(child, set()) if child else known):
            return f"Field not permitted in query: {selected}"
    for condition in conditions:
        if len(condition) == 4:
            child, field = condition[0], condition[1]
            if child not in tables.values() or field not in FIELDS.get(child, set()):
                return f"Field not permitted in query: {child}.{field}"
        elif condition[0] not in known:
            return f"Field not permitted in query: {condition[0]}"
    return None


def _matches_all(doctype: str, doc: dict[str, Any], filters: list[list[Any]]) -> bool:
    """Plain conditions on the document; [child DocType, field, op, value] on one row of
    that child table, as v16 joins it once."""
    if not all(_matches(doc, f) for f in filters if len(f) == 3):
        return False
    for table, child in TABLES.get(doctype, {}).items():
        conditions = [f[1:] for f in filters if len(f) == 4 and f[0] == child]
        rows = cast("list[dict[str, Any]]", doc.get(table) or [])
        if conditions and not any(all(_matches(r, c) for c in conditions) for r in rows):
            return False
    return True


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
        case ">=":
            return actual is not None and actual >= value
        case "<=":
            return actual is not None and actual <= value
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


def customer(name: str = "CUST-0001", **overrides: Any) -> dict[str, Any]:
    """A Customer as frappe.client.get returns it."""
    doc: dict[str, Any] = {
        "doctype": "Customer",
        "name": name,
        "customer_name": f"Customer {name}",
        "customer_type": "Company",
        "customer_group": "Commercial",
        "tax_id": "DE123456789",
        "default_currency": "EUR",
        "disabled": 0,
        "payment_terms": "Net 30",
        "modified": "2026-10-20 10:00:00.000000",
    }
    doc.update(overrides)
    return doc


def address(name: str, link_doctype: str, link_name: str, **overrides: Any) -> dict[str, Any]:
    """An Address linked to one party through a Dynamic Link row."""
    doc: dict[str, Any] = {
        "doctype": "Address",
        "name": name,
        "address_type": "Billing",
        "is_primary_address": 1,
        "address_line1": "Hauptstraße 1",
        "address_line2": None,
        "city": "Berlin",
        "pincode": "10115",
        "country": "Germany",
        "links": [
            {"doctype": "Dynamic Link", "link_doctype": link_doctype, "link_name": link_name}
        ],
    }
    doc.update(overrides)
    return doc


def sales_invoice(name: str = "ACC-SINV-2026-00001", **overrides: Any) -> dict[str, Any]:
    """A Sales Invoice as frappe.client.get returns it."""
    doc: dict[str, Any] = {
        "doctype": "Sales Invoice",
        "name": name,
        "company": COMPANY,
        "customer": "CUST-0001",
        "customer_name": "Customer CUST-0001",
        "posting_date": "2026-10-01",
        "due_date": "2026-10-31",
        "currency": "EUR",
        "net_total": 100.0,
        "grand_total": 119.0,
        "outstanding_amount": 119.0,
        "status": "Unpaid",
        "docstatus": 1,
        "is_return": 0,
        "owner": "agent@example.com",
        "modified": "2026-10-01 09:00:00.000000",
        "taxes_and_charges": "VAT 19% - EX",
        "total_taxes_and_charges": 19.0,
        "return_against": None,
        "remarks": "As agreed",
        "items": [
            {
                "doctype": "Sales Invoice Item",
                "item_code": "SKU-1",
                "item_name": "Widget SKU-1",
                "description": "<p>The widget SKU-1</p>",
                "qty": 2.0,
                "uom": "Nos",
                "rate": 50.0,
                "amount": 100.0,
                "income_account": "4000 - Sales - EX",
                "item_tax_template": None,
                "cost_center": "Main - EX",
            }
        ],
        "taxes": [
            {
                "doctype": "Sales Taxes and Charges",
                "charge_type": "On Net Total",
                "account_head": "1776 - VAT 19% - EX",
                "rate": 19.0,
                "tax_amount": 19.0,
                "description": "VAT 19%",
            }
        ],
    }
    doc.update(overrides)
    return doc


def tax_template(name: str = "VAT 19% - EX", **overrides: Any) -> dict[str, Any]:
    """A Sales Taxes and Charges Template."""
    doc: dict[str, Any] = {
        "doctype": "Sales Taxes and Charges Template",
        "name": name,
        "title": name.rsplit(" - ", 1)[0],
        "company": COMPANY,
        "is_default": 0,
        "tax_category": None,
        "disabled": 0,
        "taxes": [
            {
                "doctype": "Sales Taxes and Charges",
                "charge_type": "On Net Total",
                "account_head": "1776 - VAT 19% - EX",
                "description": "VAT 19%",
                "rate": 19.0,
                "included_in_print_rate": 0,
                "cost_center": "Main - EX",
            }
        ],
    }
    doc.update(overrides)
    return doc


def receivable(voucher_no: str, outstanding: float, **overrides: Any) -> dict[str, Any]:
    """A row of Accounts Receivable as its execute() returns it, with columns Erpel drops."""
    row: dict[str, Any] = {
        "party_type": "Customer",
        "party": "CUST-0001",
        "party_account": "1400 - Debtors - EX",
        "customer_primary_contact": "Jane Doe",
        "cost_center": "Main - EX",
        "voucher_type": "Sales Invoice",
        "voucher_no": voucher_no,
        "posting_date": "2026-09-01",
        "due_date": "2026-10-01",
        "invoiced": outstanding,
        "paid": 0.0,
        "credit_note": 0.0,
        "outstanding": outstanding,
        "currency": "EUR",
        "age": 27,
        "range0": 0.0,
        "range1": outstanding,
        "range2": 0.0,
        "range3": 0.0,
        "range4": 0.0,
        "range5": 0.0,
        "total_due": outstanding,
    }
    row.update(overrides)
    return row
