"""Nothing of a deployment in the repository (REQ-002-PRS-NF014): every host in a URL and
every email address in a tracked file is a reserved example or test name, an address that
isn't public, or a public site on PUBLIC_HOSTS. A new public site goes on the list, where a
review sees it. Credentials are gitleaks' part, in CI and in the improvement pipeline's
gate."""

import ipaddress
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The public sites the repository links to, downloads from or names: no deployment's
PUBLIC_HOSTS = frozenset(
    {
        "arc42.org",
        "claude.ai",
        "claude.com",
        "docs.astral.sh",
        "docs.github.com",
        "files.pythonhosted.org",
        "genai.owasp.org",
        "ghcr.io",
        "github.com",
        "keepachangelog.com",
        "lychee.cli.rs",
        "modelcontextprotocol.io",
        "pypi.org",
        "raw.githubusercontent.com",
        "registry.modelcontextprotocol.io",
        "semver.org",
        "slsa.dev",
        "spdx.dev",
        "static.modelcontextprotocol.io",
        "token.actions.githubusercontent.com",
        "www.apache.org",
        "www.conventionalcommits.org",
        "www.keycloak.org",
        "www.rfc-editor.org",
    }
)
# Reserved for examples and tests (RFC 2606, RFC 6761), and the private-use top-level
# domain `internal`, which no public site can have
RESERVED = ("example.com", "example.net", "example.org", "example", "test", "invalid")
PRIVATE = ("localhost", "internal")

URL = re.compile(r"[a-z][a-z0-9+.-]*://([^/\s\"'<>()`\\?#]+)", re.IGNORECASE)
EMAIL = re.compile(r"[a-z0-9._%+-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)+)", re.IGNORECASE)
NAME = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}")


def _under(host: str, domains: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in domains)


def _host(authority: str) -> str | None:
    """The host of a URL's authority, or None where it is no host name or address: a
    placeholder, a template, a single label such as a compose service."""
    host = authority.rpartition("@")[2].lower().rstrip(".,;:")
    if host.startswith("["):
        return host[1:].partition("]")[0]
    host = host.partition(":")[0].rstrip(".")
    if _ip(host) is not None or NAME.fullmatch(host):
        return host
    return None


def _ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def url_host_allowed(host: str) -> bool:
    address = _ip(host)
    if address is not None:
        return not address.is_global
    return host in PUBLIC_HOSTS or _under(host, RESERVED + PRIVATE)


def email_domain_allowed(domain: str) -> bool:
    return _under(domain.lower(), RESERVED)


def offending(text: str) -> Iterator[tuple[int, str]]:
    """Each host and email address of `text` that isn't allowed, with its line."""
    for number, line in enumerate(text.splitlines(), 1):
        for match in URL.finditer(line):
            host = _host(match.group(1))
            if host is not None and not url_host_allowed(host):
                yield number, host
        for match in EMAIL.finditer(line):
            domain = match.group(1).rstrip(".")
            if NAME.fullmatch(domain.lower()) and not email_domain_allowed(domain):
                yield number, match.group(0)


def tracked() -> list[Path]:
    names = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607 - git from PATH, as in CI
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return [ROOT / name for name in names.split("\0") if name]


def test_no_tracked_file_names_a_host_or_email_address_of_a_deployment() -> None:
    found: list[str] = []
    for path in tracked():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue  # binary, or deleted but not yet committed
        found += [f"{path.relative_to(ROOT)}:{n}: {h}" for n, h in offending(text)]
    assert found == []


def test_a_deployments_host_and_email_address_are_found() -> None:
    # Joined here, so this file doesn't name them itself
    domain = "acme-gmbh" + ".de"
    text = f"ENTERICH_ERPNEXT_URL=https://erp.{domain}\nask buchhaltung@{domain}\n"
    assert list(offending(text)) == [(1, f"erp.{domain}"), (2, f"buchhaltung@{domain}")]


def test_examples_placeholders_and_addresses_that_arent_public_pass() -> None:
    text = (
        "https://erp.example.com/mcp http://127.0.0.1:8080 http://[::1]:8080 "
        "http://10.0.0.5 http://erp.internal:8000 http://valkey:6379 "
        "https://{host}{path} agent@example.com https://user:pw@id.example.com/certs"
    )
    assert list(offending(text)) == []


def test_a_public_host_passes_only_from_the_list() -> None:
    assert url_host_allowed("github.com")
    assert not url_host_allowed("gitlab.com")
    assert not email_domain_allowed("github.com")
