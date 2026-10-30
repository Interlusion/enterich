from collections.abc import Iterator

import pytest

from tests.conftest import Logs
from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer
from tests.fakes.settings import API_KEY, API_SECRET, settings
from tests.integration.clock import TIMEZONE, freeze
from tests.integration.mcp import Session, checked_session, client


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erpnext() -> Iterator[FakeErpnext]:
    """The fake ERPNext; afterwards Enterich must have used none of its side doors
    (REQ-001-PRS-F006)."""
    fake = FakeErpnext()
    yield fake
    assert fake.doors == []


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    """The fake ERPNext a test file's session talks to; files override it with their data."""
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext, logs: Logs) -> Iterator[Session]:
    """A client's session with Enterich in TIMEZONE, checked for the API key and secret."""
    c = client(jwks, settings(timezone=TIMEZONE), erp)
    with checked_session(c, signer, logs, (API_KEY, API_SECRET)) as session:
        yield session
