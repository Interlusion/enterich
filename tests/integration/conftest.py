from collections.abc import Iterator

import pytest

from tests.conftest import Logs
from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer, token
from tests.fakes.settings import API_KEY, API_SECRET, settings
from tests.integration.clock import TIMEZONE, freeze
from tests.integration.mcp import Session, client


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erpnext() -> FakeErpnext:
    return FakeErpnext()


@pytest.fixture
def erp(erpnext: FakeErpnext) -> FakeErpnext:
    """The fake ERPNext a test file's session talks to; files override it with their data."""
    return erpnext


@pytest.fixture
def mcp(jwks: FakeJwks, signer: Signer, erp: FakeErpnext, logs: Logs) -> Iterator[Session]:
    """A client's session with Enterich in TIMEZONE. Afterwards, neither the log nor any
    answer may carry the API key, the secret or a part of the token (REQ-002-PRS-NF010)."""
    t = token(signer)
    with client(jwks, settings(timezone=TIMEZONE), erp) as c:
        session = Session(c, t)
        yield session
    seen = logs.stream.getvalue() + "".join(session.answers)
    _, payload, signature = t.split(".")
    for secret in (API_KEY, API_SECRET, payload, signature):
        assert secret not in seen
