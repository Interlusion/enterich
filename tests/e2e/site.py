"""The ERPNext site of tests/e2e/compose.yml, reached as Administrator to seed it."""

import json
from typing import Any

import httpx2

# Where scripts/erpnext-site.sh publishes the site; unset, the end-to-end tests skip.
URL_VARIABLE = "E2E_ERPNEXT_URL"
# The site's name, which ERPNext reads from the Host header, and its Administrator's
# password: both from compose.yml, for this throwaway site alone.
HOST = "e2e.localhost"
ADMIN_PASSWORD = "e2e-admin"


class SiteError(Exception):
    """ERPNext refused an Administrator call; the message carries its answer."""


class Site:
    """Administrator's REST calls, with a session cookie: seeding only, never Enterich's path."""

    def __init__(self, url: str) -> None:
        self._client = httpx2.Client(base_url=url, headers={"host": HOST}, timeout=120.0)
        self.call("login", usr="Administrator", pwd=ADMIN_PASSWORD)

    def close(self) -> None:
        self._client.close()

    def call(self, method: str, **args: Any) -> Any:
        """POST /api/method/<method>; dicts and lists go as JSON, as the desk sends them."""
        data = {k: json.dumps(v) if isinstance(v, dict | list) else v for k, v in args.items()}
        return self._answer(self._client.post(f"/api/method/{method}", data=data))

    def get_list(
        self, doctype: str, filters: dict[str, Any] | None = None, fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        params = {
            "filters": json.dumps(filters or {}),
            "fields": json.dumps(fields or ["name"]),
            "limit_page_length": "0",
        }
        return self._answer(self._client.get(f"/api/resource/{doctype}", params=params))

    def exists(self, doctype: str, filters: dict[str, Any]) -> bool:
        return bool(self.get_list(doctype, filters))

    def insert(self, doc: dict[str, Any]) -> dict[str, Any]:
        return self._answer(self._client.post(f"/api/resource/{doc['doctype']}", json=doc))

    def update(self, doctype: str, name: str, fields: dict[str, Any]) -> dict[str, Any]:
        return self._answer(self._client.put(f"/api/resource/{doctype}/{name}", json=fields))

    def _answer(self, response: httpx2.Response) -> Any:
        if response.status_code != 200:
            raise SiteError(
                f"{response.request.method} {response.request.url.path}: {response.text}"
            )
        body = response.json()
        return body.get("message", body.get("data"))
