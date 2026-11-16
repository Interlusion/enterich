from collections.abc import Iterator
from pathlib import Path

import pytest

from enterich import tools
from tests.conftest import Logs
from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer
from tests.fakes.settings import API_KEY, API_SECRET, DRAFTS_PER_HOUR, settings
from tests.integration.clock import TIMEZONE, freeze
from tests.integration.mcp import CALLED, Session, checked_session, client


def whole_suite(session: pytest.Session) -> bool:
    """Whether this run collected every integration test file, unfiltered, and all passed."""
    option = session.config.option
    filters = (option.keyword, option.markexpr, option.deselect, getattr(option, "lf", False))
    if session.testsfailed or any(filters):
        return False
    if any("::" in arg for arg in session.config.args):
        return False
    here = Path(__file__).parent
    files = {item.path for item in session.items if item.path.parent == here}
    return files == set(here.glob("test_*.py"))


@pytest.fixture(scope="session", autouse=True)
def every_operation_called(request: pytest.FixtureRequest) -> Iterator[None]:
    """After a whole integration run, every operation must have been called through
    `Session`, the client that never confirms anything (REQ-001-PRS-F013)."""
    yield
    if whole_suite(request.session):
        assert set(tools.names()) - CALLED == set()


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze(monkeypatch)


@pytest.fixture
def erpnext() -> Iterator[FakeErpnext]:
    """The fake ERPNext, setting a session cookie as a real one does; afterwards every
    request it received, read or write, must carry the agent's key, the configured Host,
    English and no cookie (REQ-002-PRS-NF006), Enterich must have used none of its side
    doors (REQ-001-PRS-F006), and each of its comments must be on a document of the DocType
    it names (REQ-001-PRS-F015)."""
    fake = FakeErpnext(set_cookie=True)
    yield fake
    for received in fake.received:
        assert received.headers["authorization"] == f"token {API_KEY}:{API_SECRET}"
        assert received.headers["host"] == settings().erpnext_host
        assert received.headers["accept-language"] == "en"
        assert "cookie" not in received.headers
    assert fake.doors == []
    for comment in fake.comments:
        assert comment["reference_name"] in fake.docs.get(comment["reference_doctype"], {})


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


@pytest.fixture
def limited(jwks: FakeJwks, signer: Signer, erp: FakeErpnext, logs: Logs) -> Iterator[Session]:
    """As `mcp`, with Enterich limited to DRAFTS_PER_HOUR drafts per hour
    (REQ-001-PRS-F019)."""
    c = client(jwks, settings(timezone=TIMEZONE, max_drafts_per_hour=str(DRAFTS_PER_HOUR)), erp)
    with checked_session(c, signer, logs, (API_KEY, API_SECRET)) as session:
        yield session
