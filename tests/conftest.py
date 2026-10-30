import io
import json
import logging
import os
from collections.abc import Iterator
from typing import Any

import pytest

from enterich import log
from tests.fakes.jwks import FakeJwks, Signer, rsa_signer
from tests.fakes.settings import API_KEY, API_SECRET


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def signer() -> Signer:
    return rsa_signer()


@pytest.fixture
def jwks(signer: Signer) -> FakeJwks:
    return FakeJwks([signer])


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No ENTERICH_ variable from the shell, and the logging setup restored afterwards."""
    for name in list(os.environ):
        if name.startswith("ENTERICH_"):
            monkeypatch.delenv(name)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


KNOWN_EVENTS = {"start", "operation", "rejection", "jwks", "error", "library"}


class Logs:
    def __init__(self) -> None:
        self.stream = io.StringIO()

    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def events(self, name: str) -> list[dict[str, Any]]:
        return [line for line in self.lines() if line["event"] == name]


@pytest.fixture
def logs() -> Iterator[Logs]:
    captured = Logs()
    log.configure("DEBUG", captured.stream)
    yield captured
    lines = captured.lines()  # every line parses as JSON
    assert {line["event"] for line in lines} <= KNOWN_EVENTS
    text = captured.stream.getvalue()
    assert API_KEY not in text
    assert API_SECRET not in text
