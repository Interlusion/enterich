import pytest

from tests.fakes.erpnext import FakeErpnext
from tests.fakes.jwks import FakeJwks, Signer, rsa_signer


@pytest.fixture
def signer() -> Signer:
    return rsa_signer()


@pytest.fixture
def jwks(signer: Signer) -> FakeJwks:
    return FakeJwks([signer])


@pytest.fixture
def erpnext() -> FakeErpnext:
    return FakeErpnext()
