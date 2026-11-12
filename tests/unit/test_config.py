"""REQ-002-PRS-NF005: configuration from the environment."""

import pytest

from enterich.config import ConfigError, load
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
            env.pop(f"ENTERICH_{name}", None)
        else:
            env[f"ENTERICH_{name}"] = value
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
    assert s.max_drafts_per_hour is None
    assert s.warnings == ()


@pytest.mark.parametrize(("value", "limit"), [("1", 1), (" 20 ", 20), ("1000", 1000)])
def test_a_limit_of_drafts_per_hour_is_a_whole_number(value: str, limit: int) -> None:
    s = load({**ENV, "ENTERICH_MAX_DRAFTS_PER_HOUR": value}, ("list_items",))
    assert s.max_drafts_per_hour == limit


def test_the_listen_address_comes_from_the_environment() -> None:
    s = load({**ENV, "ENTERICH_HOST": " 127.0.0.1 "}, ("list_items",))
    assert s.host == "127.0.0.1"


@pytest.mark.parametrize("port", [1, 65535])
def test_the_listen_port_may_be_any_from_1_to_65535(port: int) -> None:
    s = load({**ENV, "ENTERICH_PORT": str(port)}, ("list_items",))
    assert s.port == port


@pytest.mark.parametrize(
    "value",
    [
        "",
        "  ",
        "erp example.com",
        "erp.example.com/x",
        "user@erp",
        "erp.example.com:",
        "erp.example.com:abc",
    ],
)
def test_an_empty_or_invalid_erpnext_host_stops_enterich(value: str) -> None:
    assert problems(ERPNEXT_HOST=value) == [
        "ENTERICH_ERPNEXT_HOST: must be a host name or IP address, optionally with a port"
    ]


@pytest.mark.parametrize(
    "value", ["erp.example.com", "erp.internal:8000", "10.0.0.5", "[::1]:8080"]
)
def test_an_erpnext_host_may_carry_a_port(value: str) -> None:
    assert load({**ENV, "ENTERICH_ERPNEXT_HOST": value}, ("list_items",)).erpnext_host == value


@pytest.mark.parametrize("name", REQUIRED)
def test_each_required_variable_is_named_when_missing(name: str) -> None:
    assert problems(**{name: None}) == [f"ENTERICH_{name}: required"]


def test_all_problems_are_reported_at_once() -> None:
    found = problems(ISSUER=None, CLOCK_LEEWAY="61", TIMEZONE="Mars/Base")
    assert [p.split(":")[0] for p in found] == [
        "ENTERICH_ISSUER",
        "ENTERICH_CLOCK_LEEWAY",
        "ENTERICH_TIMEZONE",
    ]


HTTPS_ONLY = "must use https (http only for a loopback host)"
CANONICAL = "must be canonical: lower-case scheme and host, no default port"
PLAIN_PATH = "must have a path of plain segments without a trailing slash, e.g. /mcp"
VALID_HOST = "must be an http or https URL with a valid host"
ASYMMETRIC = (
    "must list asymmetric algorithms only: "
    "ES256, ES384, ES512, EdDSA, PS256, PS384, PS512, RS256, RS384, RS512"
)
IANA = "must be an IANA time zone name, e.g. Europe/Berlin"


@pytest.mark.parametrize(
    ("name", "value", "rule"),
    [
        ("ISSUER", "http://id.example.com/realms/example", HTTPS_ONLY),
        ("JWKS_URL", "http://id.example.com/certs", HTTPS_ONLY),
        ("RESOURCE_URL", "https://ERP.example.com/mcp/", CANONICAL),
        ("RESOURCE_URL", "https://erp.example.com/mcp/", PLAIN_PATH),
        ("RESOURCE_URL", "HTTPS://erp.example.com/mcp", CANONICAL),
        ("RESOURCE_URL", "https://erp.example.com:443/mcp", CANONICAL),
        ("RESOURCE_URL", "https://erp.example.com", PLAIN_PATH),
        ("RESOURCE_URL", "https://erp.example.com/mcp?x=1", "must not have a query or fragment"),
        ("RESOURCE_URL", "https://erp.example.com/mcp#top", "must not have a query or fragment"),
        (
            "RESOURCE_URL",
            "https://user:pw@erp.example.com/mcp",
            "must not contain user information",
        ),
        ("ERPNEXT_URL", "ftp://erp.example.com", VALID_HOST),
        ("ERPNEXT_PUBLIC_URL", "erp.example.com", VALID_HOST),
        ("CLOCK_LEEWAY", "61", "must be from 0 to 60"),
        ("CLOCK_LEEWAY", "-1", "must be from 0 to 60"),
        ("CLOCK_LEEWAY", "five", "must be a whole number from 0 to 60"),
        ("TOKEN_ALGORITHMS", "HS256", ASYMMETRIC),
        ("TOKEN_ALGORITHMS", "RS256,none", ASYMMETRIC),
        ("TIMEZONE", "Europe/Nowhere", IANA),
        ("TOOLS", "list_items,drop_database", "unknown operations: drop_database"),
        ("PORT", "0", "must be from 1 to 65535"),
        ("PORT", "65536", "must be from 1 to 65535"),
        ("LOG_LEVEL", "TRACE", "must be one of DEBUG, INFO, WARNING, ERROR"),
        ("REQUIRED_SCOPES", "", "must name at least one scope"),
        ("REQUIRED_SCOPES", "   ", "must name at least one scope"),
        ("RESOURCE_URL", "https://erp.example.com:/mcp", "must not have an empty port"),
        ("RESOURCE_URL", "https://erp.example.com/m%63p", PLAIN_PATH),
        ("RESOURCE_URL", "https://erp.example.com/a/../mcp", PLAIN_PATH),
        ("RESOURCE_URL", "https://erp.example.com/./mcp", PLAIN_PATH),
        ("RESOURCE_URL", "https://erp.example.com/mcp;x", PLAIN_PATH),
        ("RESOURCE_URL", "https://erp.example.com//mcp", PLAIN_PATH),
        ("RESOURCE_URL", "https://999.1.1.1/mcp", "must be a URL the metadata can publish"),
        ("RESOURCE_URL", "https://1.1/mcp", "must be in the form the metadata publishes"),
        ("ISSUER", "https://id exa.com/realms/example", VALID_HOST),
        ("ISSUER", "https://ID.example.com/realms/example", CANONICAL),
        ("JWKS_URL", "https://id exa.com/certs", VALID_HOST),
        ("JWKS_URL", "https://id.example.com:/certs", "must not have an empty port"),
        ("JWKS_URL", "https://id.example.com:x/certs", "must be a URL"),
        ("ERPNEXT_URL", "http://erp internal:8080", VALID_HOST),
        ("TIMEZONE", "a" * 300, IANA),
        ("MAX_DRAFTS_PER_HOUR", "0", "must be from 1 to 1000"),
        ("MAX_DRAFTS_PER_HOUR", "1001", "must be from 1 to 1000"),
        ("MAX_DRAFTS_PER_HOUR", "-5", "must be from 1 to 1000"),
        ("MAX_DRAFTS_PER_HOUR", "ten", "must be a whole number from 1 to 1000"),
        ("MAX_DRAFTS_PER_HOUR", "", "must be a whole number from 1 to 1000"),
    ],
)
def test_invalid_values_stop_enterich_with_name_and_rule(name: str, value: str, rule: str) -> None:
    assert problems(**{name: value}) == [f"ENTERICH_{name}: {rule}"]


def test_http_urls_are_allowed_for_loopback_hosts() -> None:
    s = load(
        {
            **ENV,
            "ENTERICH_RESOURCE_URL": "http://127.0.0.1:8000/mcp",
            "ENTERICH_ISSUER": "http://localhost:8180/realms/example",
            "ENTERICH_JWKS_URL": "http://[::1]:8180/certs",
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
    s = load({**ENV, "ENTERICH_ERPNEXT_URL": "http://erp.internal:8080"}, ())
    assert s.warnings == ("ENTERICH_ERPNEXT_URL uses http: the API key travels unencrypted",)


def test_http_erpnext_public_url_to_another_host_loads() -> None:
    s = load({**ENV, "ENTERICH_ERPNEXT_PUBLIC_URL": "http://erp.internal"}, ())
    assert s.erpnext_public_url == "http://erp.internal"
    assert s.warnings == ()


@pytest.mark.parametrize(
    ("value", "url"),
    [
        ("https://erp.example.com/", "https://erp.example.com"),
        ("http://erp.internal/X/", "http://erp.internal/X"),
    ],
)
def test_a_trailing_slash_is_dropped_from_the_erpnext_urls(value: str, url: str) -> None:
    s = load({**ENV, "ENTERICH_ERPNEXT_URL": value, "ENTERICH_ERPNEXT_PUBLIC_URL": value}, ())
    assert (s.erpnext_url, s.erpnext_public_url) == (url, url)


def test_unknown_enterich_variables_are_reported_as_warnings() -> None:
    s = load({**ENV, "ENTERICH_TOOL": "list_items"}, ("list_items",))
    assert s.warnings == ("ENTERICH_TOOL is not a known variable and is ignored",)
    assert s.tools == ("list_items",)


def test_tools_set_limits_the_operations() -> None:
    s = load({**ENV, "ENTERICH_TOOLS": " list_items , "}, ("list_items", "get_item"))
    assert s.tools == ("list_items",)
