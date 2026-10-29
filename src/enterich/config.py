"""Configuration from `ENTERICH_*` environment variables, validated once at start.

REQ-002-PRS-NF005: every missing or invalid variable is reported by name and
rule, never with the value of a secret.
"""

import re
from collections.abc import Collection, Mapping
from ipaddress import ip_address
from typing import Literal
from urllib.parse import SplitResult, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.auth.settings import AuthSettings
from pydantic import BaseModel, ConfigDict, SecretStr, ValidationError

PREFIX = "ENTERICH_"

# Asymmetric JWS algorithms only (ADR-003); never HS* or none.
ALLOWED_ALGORITHMS = frozenset(
    {"RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA"}
)
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
MAX_CLOCK_LEEWAY = 60

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Unreserved characters only, no empty, "." or ".." segments, so the path the
# client sends is the path the wrapper and the SDK compare.
CANONICAL_PATH = re.compile(r"(/[A-Za-z0-9_~-][A-Za-z0-9._~-]*)+")
HOST_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*")

KNOWN = frozenset(
    {
        "RESOURCE_URL",
        "ISSUER",
        "JWKS_URL",
        "CLIENT_ID",
        "SUBJECT",
        "REQUIRED_SCOPES",
        "TOKEN_ALGORITHMS",
        "CLOCK_LEEWAY",
        "ERPNEXT_URL",
        "ERPNEXT_HOST",
        "ERPNEXT_PUBLIC_URL",
        "ERPNEXT_API_KEY",
        "ERPNEXT_API_SECRET",
        "COMPANY",
        "TOOLS",
        "TIMEZONE",
        "HOST",
        "PORT",
        "LOG_LEVEL",
    }
)


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    resource_url: str
    mcp_path: str
    issuer: str
    jwks_url: str
    client_id: str
    subject: str
    required_scopes: tuple[str, ...]
    token_algorithms: tuple[str, ...]
    clock_leeway: int
    erpnext_url: str
    erpnext_host: str
    erpnext_public_url: str
    erpnext_api_key: SecretStr
    erpnext_api_secret: SecretStr
    company: str
    tools: tuple[str, ...]
    timezone: ZoneInfo
    host: str
    port: int
    log_level: LogLevel
    warnings: tuple[str, ...] = ()

    @property
    def secrets(self) -> tuple[str, str]:
        """The values no answer or log line may carry."""
        return (
            self.erpnext_api_key.get_secret_value(),
            self.erpnext_api_secret.get_secret_value(),
        )


class ConfigError(Exception):
    """Enterich can't start; `problems` names each variable and its rule."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("invalid configuration: " + "; ".join(problems))
        self.problems = problems


def load(env: Mapping[str, str], operations: Collection[str]) -> Settings:
    """Build the settings from `env`; `operations` are the names `ENTERICH_TOOLS` may use."""
    reader = _Reader(env)
    resource = reader.url("RESOURCE_URL", canonical=True)
    issuer = reader.url("ISSUER")
    jwks = reader.url("JWKS_URL")
    erpnext = reader.url("ERPNEXT_URL", https_only=False)
    public = reader.url("ERPNEXT_PUBLIC_URL", https_only=False)

    settings = {
        "resource_url": resource.geturl() if resource else "",
        "mcp_path": resource.path if resource else "",
        "issuer": issuer.geturl() if issuer else "",
        "jwks_url": jwks.geturl() if jwks else "",
        "client_id": reader.text("CLIENT_ID"),
        "subject": reader.text("SUBJECT"),
        "required_scopes": reader.scopes(),
        "token_algorithms": reader.algorithms(),
        "clock_leeway": reader.integer("CLOCK_LEEWAY", "5", 0, MAX_CLOCK_LEEWAY),
        "erpnext_url": erpnext.geturl().rstrip("/") if erpnext else "",
        "erpnext_host": reader.host("ERPNEXT_HOST", erpnext.netloc if erpnext else ""),
        "erpnext_public_url": public.geturl().rstrip("/") if public else "",
        "erpnext_api_key": SecretStr(reader.text("ERPNEXT_API_KEY")),
        "erpnext_api_secret": SecretStr(reader.text("ERPNEXT_API_SECRET")),
        "company": reader.text("COMPANY"),
        "tools": reader.tools(operations),
        "timezone": reader.timezone(),
        "host": reader.optional("HOST", "0.0.0.0"),  # noqa: S104 - a container listens on all addresses
        "port": reader.integer("PORT", "8000", 1, 65535),
        "log_level": reader.choice("LOG_LEVEL", "INFO", LOG_LEVELS),
    }
    if resource and issuer:
        reader.as_published(resource.geturl(), issuer.geturl())
    if reader.problems:
        raise ConfigError(reader.problems)

    warnings = [
        f"{PREFIX}{name} is not a known variable and is ignored" for name in reader.unknown()
    ]
    if erpnext and erpnext.scheme == "http" and not _is_loopback(erpnext.hostname):
        warnings.append(f"{PREFIX}ERPNEXT_URL uses http: the API key travels unencrypted")
    return Settings.model_validate({**settings, "warnings": tuple(warnings)})


class _Reader:
    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = {k.removeprefix(PREFIX): v for k, v in env.items() if k.startswith(PREFIX)}
        self.problems: list[str] = []

    def unknown(self) -> list[str]:
        return sorted(set(self.env) - KNOWN)

    def fail(self, name: str, rule: str) -> None:
        self.problems.append(f"{PREFIX}{name}: {rule}")

    def text(self, name: str) -> str:
        value = self.env.get(name, "").strip()
        if not value:
            self.fail(name, "required")
        return value

    def optional(self, name: str, default: str) -> str:
        value = self.env.get(name)
        return default if value is None else value.strip()

    def host(self, name: str, default: str) -> str:
        """A Host header value: a host name or IP address, optionally with a port."""
        if name not in self.env:
            return default  # checked as part of its URL
        value = self.optional(name, default)
        try:
            parsed = urlsplit(f"//{value}")
            parsed.port  # noqa: B018 - raises for a port that isn't a number
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.netloc != value
            or parsed.username is not None
            or value.endswith(":")
            or not _valid_host(parsed.hostname)
        ):
            self.fail(name, "must be a host name or IP address, optionally with a port")
        return value

    def integer(self, name: str, default: str, low: int, high: int) -> int:
        raw = self.optional(name, default)
        try:
            value = int(raw)
        except ValueError:
            self.fail(name, f"must be a whole number from {low} to {high}")
            return low
        if not low <= value <= high:
            self.fail(name, f"must be from {low} to {high}")
        return value

    def choice(self, name: str, default: str, choices: tuple[str, ...]) -> LogLevel:
        value = self.optional(name, default).upper()
        if value not in choices:
            self.fail(name, "must be one of " + ", ".join(choices))
            return "INFO"
        return value  # pyright: ignore[reportReturnType] - checked against LOG_LEVELS

    def scopes(self) -> tuple[str, ...]:
        scopes = tuple(self.optional("REQUIRED_SCOPES", "openid").split())
        if not scopes:
            self.fail("REQUIRED_SCOPES", "must name at least one scope")
        return scopes

    def algorithms(self) -> tuple[str, ...]:
        names = tuple(a.strip() for a in self.optional("TOKEN_ALGORITHMS", "RS256").split(","))
        if any(n not in ALLOWED_ALGORITHMS for n in names):
            self.fail(
                "TOKEN_ALGORITHMS",
                "must list asymmetric algorithms only: " + ", ".join(sorted(ALLOWED_ALGORITHMS)),
            )
        return names

    def tools(self, operations: Collection[str]) -> tuple[str, ...]:
        raw = self.env.get("TOOLS")
        if raw is None:
            return tuple(sorted(operations))
        names = tuple(n.strip() for n in raw.split(",") if n.strip())
        unknown = sorted(set(names) - set(operations))
        if unknown:
            self.fail("TOOLS", "unknown operations: " + ", ".join(unknown))
        return names

    def timezone(self) -> ZoneInfo:
        name = self.optional("TIMEZONE", "UTC")
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError, ValueError, OSError:
            self.fail("TIMEZONE", "must be an IANA time zone name, e.g. Europe/Berlin")
            return ZoneInfo("UTC")

    def url(
        self, name: str, *, https_only: bool = True, canonical: bool = False
    ) -> SplitResult | None:
        raw = self.text(name)
        if not raw:
            return None
        try:
            url = urlsplit(raw)
            port = url.port
        except ValueError:
            self.fail(name, "must be a URL")
            return None
        if url.scheme not in ("http", "https") or not _valid_host(url.hostname):
            self.fail(name, "must be an http or https URL with a valid host")
            return None
        if url.netloc.endswith(":"):
            self.fail(name, "must not have an empty port")
            return None
        if url.username is not None or url.password is not None:
            self.fail(name, "must not contain user information")
            return None
        if https_only and url.scheme != "https" and not _is_loopback(url.hostname):
            self.fail(name, "must use https (http only for a loopback host)")
            return None
        if url.query or url.fragment or raw.endswith(("?", "#")):
            self.fail(name, "must not have a query or fragment")
            return None
        if canonical:
            default_port = {"http": 80, "https": 443}[url.scheme]
            scheme_and_host = raw[: len(url.scheme) + 3 + len(url.netloc)]
            if scheme_and_host != scheme_and_host.lower() or port == default_port:
                self.fail(name, "must be canonical: lower-case scheme and host, no default port")
                return None
            if not CANONICAL_PATH.fullmatch(url.path):
                self.fail(
                    name,
                    "must have a path of plain segments without a trailing slash, e.g. /mcp",
                )
                return None
        return url

    def as_published(self, resource: str, issuer: str) -> None:
        """The SDK publishes both URLs in the metadata; they must come out unchanged."""
        try:
            sdk = AuthSettings(
                issuer_url=issuer,  # pyright: ignore[reportArgumentType] - pydantic parses it
                resource_server_url=resource,  # pyright: ignore[reportArgumentType]
                validate_token_resource=False,
            )
        except ValidationError:
            self.fail("RESOURCE_URL", "must be a URL the metadata can publish")
            return
        if str(sdk.resource_server_url) != resource:
            self.fail("RESOURCE_URL", "must be in the form the metadata publishes")
        if str(sdk.issuer_url) != issuer:
            self.fail("ISSUER", "must be canonical: lower-case scheme and host, no default port")


def _valid_host(host: str | None) -> bool:
    if not host:
        return False
    try:
        ip_address(host)
    except ValueError:
        return HOST_NAME.fullmatch(host) is not None
    return True


def _is_loopback(host: str | None) -> bool:
    if host is None:
        return False
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False
