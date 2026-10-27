import logging
import os
from collections.abc import Iterator

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No ERPEL_ variable from the shell, and the logging setup restored afterwards."""
    for name in list(os.environ):
        if name.startswith("ERPEL_"):
            monkeypatch.delenv(name)
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
