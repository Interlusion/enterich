"""The configuration guide's site settings: each field it names exists on the pinned ERPNext,
the seed sets the switches as the guide says, and the switch that closes a door does close
it to the agent user's key. The security policy holds the docs in scope: a guide whose
instructions leave a deployment open (`SECURITY.md`). A wrong name in the guide, or one an
ERPNext release renames, fails here instead of leaving a site open, as `disable_mcp_server`
did.

The guide is read from the checkout: the end-to-end tests run on the runner, never in the
image."""

import re
from pathlib import Path
from typing import Any

import httpx2

from tests.e2e.seed import AGENT, SITE_SETTINGS, Seed, ensure, rules
from tests.e2e.site import HOST, Site

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guides" / "configuration.md"
# Names in the guide's site settings that are no field, each with why it is named there
NOT_FIELDS = {
    "outside_text": "Enterich's result field, not ERPNext's",
    "disable_mcp_server": "the site config key the guide says Frappe doesn't read",
}


def site_settings_text() -> str:
    """The guide's list of site settings, up to the next heading."""
    text = GUIDE.read_text(encoding="utf-8")
    return text.split("- **Site settings:**", 1)[1].split("\n## ", 1)[0]


def named() -> set[str]:
    """Every name in backticks the guide's site settings give that could be a field."""
    return set(re.findall(r"`([a-z][a-z0-9]*(?:_[a-z0-9]+)+)`", site_settings_text()))


def fields(site: Site, names: set[str]) -> dict[str, set[str]]:
    """Each name's DocTypes on the site, from the DocType meta ERPNext holds."""
    rows = site.get_list("DocField", {"fieldname": ["in", sorted(names)]}, ["parent", "fieldname"])
    found: dict[str, set[str]] = {}
    for row in rows:
        found.setdefault(row["fieldname"], set()).add(row["parent"])
    return found


def test_every_field_the_guides_site_settings_name_exists(site: Site) -> None:
    names = named() - set(NOT_FIELDS)
    assert names, "the guide's site settings name no field"
    assert sorted(names - set(fields(site, names))) == []


def test_the_seeds_switches_are_fields_the_guide_names(site: Site) -> None:
    held = fields(site, {field for _, field in SITE_SETTINGS})
    for doctype, field in SITE_SETTINGS:
        assert doctype in held.get(field, set()), f"{doctype} has no field {field}"
        assert field in named(), f"the guide's site settings don't name {field}"


def test_the_seed_sets_the_guides_switches(site: Site, seeded: Seed) -> None:
    for (doctype, field), value in SITE_SETTINGS.items():
        held = site.call("frappe.client.get_single_value", doctype=doctype, field=field)
        assert (doctype, field, held) == (doctype, field, value)


def test_frappes_mcp_endpoint_doesnt_answer_the_agent_users_key(
    agent: httpx2.Client,
) -> None:
    initialize: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "e2e", "version": "0"},
        },
    }
    answer = agent.post(
        "/api/v2/mcp",
        json=initialize,
        headers={"accept": "application/json, text/event-stream"},
    )
    assert answer.status_code == 404


SHARER = "enterich-sharer@example.com"
SHARER_ROLE = "Enterich Test Sharer"


def test_a_user_with_share_rights_cant_share_a_document_with_the_agent_user(
    url: str, site: Site, seeded: Seed
) -> None:
    """With `disable_document_sharing`, a share can't pass the agent user rights its role
    lacks, such as submit; Administrator is exempt in Frappe, so another user tries."""
    ensure(site, "Role", {"role_name": SHARER_ROLE}, desk_access=1)
    # Frappe lets a user share only the rights it holds
    rules(site, SHARER_ROLE, {"Sales Invoice": {"read", "submit", "share"}})
    ensure(
        site,
        "User",
        {"email": SHARER},
        first_name="Sharer",
        user_type="System User",
        send_welcome_email=0,
        roles=[{"role": SHARER_ROLE}],
    )
    keys = site.call("frappe.core.doctype.user.user.generate_keys", user=SHARER)
    key = f"token {keys['api_key']}:{keys['api_secret']}"
    share = {
        "doctype": "Sales Invoice",
        "name": seeded.sales_invoice,
        "user": AGENT,
        "read": 1,
        "submit": 1,
    }
    with httpx2.Client(base_url=url, headers={"host": HOST, "authorization": key}) as sharer:
        answer = sharer.post("/api/method/frappe.share.add", data=share)
    assert answer.status_code == 403
    assert not site.get_list("DocShare", {"user": AGENT, "share_doctype": "Sales Invoice"})
