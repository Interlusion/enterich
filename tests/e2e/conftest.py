import pytest

from tests.fakes.erpnext import FakeErpnext


@pytest.fixture
def erpnext() -> FakeErpnext:
    return FakeErpnext()
