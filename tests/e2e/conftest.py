import os
from collections.abc import Generator, Iterator
from contextlib import contextmanager

import httpx2
import pytest

from tests.conftest import Logs
from tests.e2e.seed import COMPANY, TIMEZONE, Seed, seed
from tests.e2e.site import HOST, URL_VARIABLE, Site
from tests.fakes.jwks import FakeJwks, Signer
from tests.fakes.settings import settings
from tests.integration.mcp import Session, checked_session, client


@pytest.fixture(scope="session")
def url() -> str:
    """The site's URL; without it every end-to-end test skips (scripts/erpnext-site.sh)."""
    value = os.environ.get(URL_VARIABLE)
    if not value:
        pytest.skip(f"{URL_VARIABLE} unset: no ERPNext site (scripts/erpnext-site.sh up)")
    return value


@pytest.fixture(scope="session")
def site(url: str) -> Iterator[Site]:
    s = Site(url)
    yield s
    s.close()


@pytest.fixture(scope="session")
def seeded(site: Site) -> Seed:
    return seed(site)


@contextmanager
def session(
    url: str, seeded: Seed, jwks: FakeJwks, signer: Signer, logs: Logs, **overrides: str
) -> Generator[Session]:
    """A client's session with Enterich, which calls the site as the agent user; checked
    for the agent's key and secret."""
    s = settings(
        erpnext_url=url,
        erpnext_host=HOST,
        erpnext_api_key=seeded.api_key,
        erpnext_api_secret=seeded.api_secret,
        company=COMPANY,
        timezone=TIMEZONE,
        **overrides,
    )
    with checked_session(
        client(jwks, s), signer, logs, (seeded.api_key, seeded.api_secret)
    ) as checked:
        yield checked


@pytest.fixture
def mcp(url: str, seeded: Seed, jwks: FakeJwks, signer: Signer, logs: Logs) -> Iterator[Session]:
    with session(url, seeded, jwks, signer, logs) as checked:
        yield checked


@pytest.fixture
def limited(
    url: str, seeded: Seed, jwks: FakeJwks, signer: Signer, logs: Logs
) -> Iterator[Session]:
    """As `mcp`, with Enterich limited to one draft of each DocType per hour."""
    with session(url, seeded, jwks, signer, logs, max_drafts_per_hour="1") as checked:
        yield checked


@pytest.fixture(scope="session")
def agent(url: str, seeded: Seed) -> Iterator[httpx2.Client]:
    """The agent user's key used directly, without Enterich: what ERPNext's role allows."""
    key = f"token {seeded.api_key}:{seeded.api_secret}"
    with httpx2.Client(
        base_url=url, headers={"host": HOST, "authorization": key}, timeout=120.0
    ) as client:
        yield client
