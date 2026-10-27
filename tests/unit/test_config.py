"""REQ-002-PRS-NF005: configuration from the environment."""

import pytest

from erpel.config import KNOWN, ConfigError, load
from tests.fakes.settings import API_KEY, API_SECRET, ENV

REQUIRED = [
    "RESOURCE_URL",
    "ISSUER",
    "JWKS_URL",
    "CLIENT_ID",
    "SUBJECT",
    "ERPNEXT_URL",
    "ERPNEXT_PUBLIC_URL",
    "ERPNEXT_API_KEY",
    "ERPNEXT_API_SECRET",
    "COMPANY",
]


def problems(**overrides: str | None) -> list[str]:
    env = dict(ENV)
    for name, value in overrides.items():
        if value is None:
            env.pop(f"ERPEL_{name}", None)
        else:
            env[f"ERPEL_{name}"] = value
    with pytest.raises(ConfigError) as caught:
        load(env, ("list_items",))
    return caught.value.problems


def test_example_configuration_loads_with_defaults() -> None:
    s = load(ENV, ("list_items", "get_item"))
    assert s.mcp_path == "/mcp"
    assert s.required_scopes == ("openid",)
    assert s.token_algorithms == ("RS256",)
    assert s.clock_leeway == 5
    assert s.erpnext_host == "127.0.0.1:8080"
    assert s.tools == ("get_item", "list_items")
    assert str(s.timezone) == "UTC"
    assert (s.host, s.port, s.log_level) == ("0.0.0.0", 8000, "INFO")
    assert s.warnings == ()


@pytest.mark.parametrize("value", ["", "  ", "erp example.com", "erp.example.com/x", "user@erp"])
def test_an_empty_or_invalid_erpnext_host_stops_erpel(value: str) -> None:
    assert [p.split(":")[0] for p in problems(ERPNEXT_HOST=value)] == ["ERPEL_ERPNEXT_HOST"]


@pytest.mark.parametrize(
    "value", ["erp.example.com", "erp.internal:8000", "10.0.0.5", "[::1]:8080"]
)
def test_an_erpnext_host_may_carry_a_port(value: str) -> None:
    assert load({**ENV, "ERPEL_ERPNEXT_HOST": value}, ("list_items",)).erpnext_host == value


@pytest.mark.parametrize("name", REQUIRED)
def test_each_required_variable_is_named_when_missing(name: str) -> None:
    assert problems(**{name: None}) == [f"ERPEL_{name}: required"]


def test_all_problems_are_reported_at_once() -> None:
    found = problems(ISSUER=None, CLOCK_LEEWAY="61", TIMEZONE="Mars/Base")
    assert [p.split(":")[0] for p in found] == [
        "ERPEL_ISSUER",
        "ERPEL_CLOCK_LEEWAY",
        "ERPEL_TIMEZONE",
    ]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ISSUER", "http://id.example.com/realms/example"),
        ("JWKS_URL", "http://id.example.com/certs"),
        ("RESOURCE_URL", "https://ERP.example.com/mcp/"),
        ("RESOURCE_URL", "https://erp.example.com/mcp/"),
        ("RESOURCE_URL", "HTTPS://erp.example.com/mcp"),
        ("RESOURCE_URL", "https://erp.example.com:443/mcp"),
        ("RESOURCE_URL", "https://erp.example.com"),
        ("RESOURCE_URL", "https://erp.example.com/mcp?x=1"),
        ("RESOURCE_URL", "https://erp.example.com/mcp#top"),
        ("RESOURCE_URL", "https://user:pw@erp.example.com/mcp"),
        ("ERPNEXT_URL", "ftp://erp.example.com"),
        ("ERPNEXT_PUBLIC_URL", "erp.example.com"),
        ("CLOCK_LEEWAY", "61"),
        ("CLOCK_LEEWAY", "-1"),
        ("CLOCK_LEEWAY", "five"),
        ("TOKEN_ALGORITHMS", "HS256"),
        ("TOKEN_ALGORITHMS", "RS256,none"),
        ("TIMEZONE", "Europe/Nowhere"),
        ("TOOLS", "list_items,drop_database"),
        ("PORT", "0"),
        ("LOG_LEVEL", "TRACE"),
        ("REQUIRED_SCOPES", ""),
        ("REQUIRED_SCOPES", "   "),
        ("RESOURCE_URL", "https://erp.example.com:/mcp"),
        ("RESOURCE_URL", "https://erp.example.com/m%63p"),
        ("RESOURCE_URL", "https://erp.example.com/a/../mcp"),
        ("RESOURCE_URL", "https://erp.example.com/./mcp"),
        ("RESOURCE_URL", "https://erp.example.com/mcp;x"),
        ("RESOURCE_URL", "https://erp.example.com//mcp"),
        ("ISSUER", "https://id exa.com/realms/example"),
        ("ISSUER", "https://ID.example.com/realms/example"),
        ("JWKS_URL", "https://id exa.com/certs"),
        ("JWKS_URL", "https://id.example.com:/certs"),
        ("ERPNEXT_URL", "http://erp internal:8080"),
        ("TIMEZONE", "a" * 300),
    ],
)
def test_invalid_values_stop_erpel_with_name_and_rule(name: str, value: str) -> None:
    found = problems(**{name: value})
    assert len(found) == 1
    assert found[0].startswith(f"ERPEL_{name}: ")


def test_http_urls_are_allowed_for_loopback_hosts() -> None:
    s = load(
        {
            **ENV,
            "ERPEL_RESOURCE_URL": "http://127.0.0.1:8000/mcp",
            "ERPEL_ISSUER": "http://localhost:8180/realms/example",
            "ERPEL_JWKS_URL": "http://[::1]:8180/certs",
        },
        (),
    )
    assert s.resource_url == "http://127.0.0.1:8000/mcp"


def test_messages_never_contain_secrets() -> None:
    found = problems(ERPNEXT_API_KEY=" ", TIMEZONE="x")
    found_text = " ".join(found)
    assert API_KEY not in found_text
    assert API_SECRET not in found_text
    s = load(ENV, ())
    assert API_KEY not in repr(s)
    assert API_SECRET not in repr(s)
    assert API_SECRET not in str(s.model_dump())


def test_http_erpnext_url_to_another_host_warns() -> None:
    s = load({**ENV, "ERPEL_ERPNEXT_URL": "http://erp.internal:8080"}, ())
    assert s.warnings == ("ERPEL_ERPNEXT_URL uses http: the API key travels unencrypted",)


def test_unknown_erpel_variables_are_reported_as_warnings() -> None:
    s = load({**ENV, "ERPEL_TOOL": "list_items"}, ("list_items",))
    assert s.warnings == ("ERPEL_TOOL is not a known variable and is ignored",)
    assert s.tools == ("list_items",)


def test_tools_set_limits_the_operations() -> None:
    s = load({**ENV, "ERPEL_TOOLS": " list_items , "}, ("list_items", "get_item"))
    assert s.tools == ("list_items",)


def test_the_configuration_guide_lists_every_variable() -> None:
    with open("docs/guides/configuration.md", encoding="utf-8") as guide:
        text = guide.read()
    for name in KNOWN:
        assert f"`ERPEL_{name}`" in text
