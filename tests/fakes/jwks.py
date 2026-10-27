"""A fake JWKS endpoint and tokens signed by its keys."""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from tests.fakes.settings import CLIENT_ID, ISSUER, RESOURCE_URL, SUBJECT


@dataclass
class Signer:
    kid: str
    key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey
    alg: str

    def jwk(self) -> dict[str, Any]:
        algorithm = jwt.get_algorithm_by_name(self.alg)
        public = algorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "use": "sig", "alg": self.alg}


def rsa_signer(kid: str = "key-1") -> Signer:
    return Signer(kid, rsa.generate_private_key(public_exponent=65537, key_size=2048), "RS256")


def ec_signer(kid: str = "key-ec") -> Signer:
    return Signer(kid, ec.generate_private_key(ec.SECP256R1()), "ES256")


def claims(**overrides: Any) -> dict[str, Any]:
    """The claims of a valid access token for the agent identity; None drops a claim."""
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": ISSUER,
        "aud": [RESOURCE_URL, "account"],
        "azp": CLIENT_ID,
        "sub": SUBJECT,
        "typ": "Bearer",
        "iat": now,
        "exp": now + 300,
        "scope": "openid profile",
        "sid": "00000000-0000-0000-0000-0000000000aa",
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def token(signer: Signer, headers: dict[str, Any] | None = None, **overrides: Any) -> str:
    return jwt.encode(
        claims(**overrides),
        signer.key,
        algorithm=signer.alg,
        headers={"kid": signer.kid, **(headers or {})},
    )


@dataclass
class FakeJwks:
    """Serves the signers' public keys; counts fetches; can be taken down."""

    signers: list[Signer]
    extra_keys: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    down: bool = False
    fetches: int = 0
    requested: list[str] = field(default_factory=list[str])

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requested.append(str(request.url))
        self.fetches += 1
        if self.down:
            return httpx2.Response(503)
        keys = [s.jwk() for s in self.signers] + self.extra_keys
        return httpx2.Response(200, json={"keys": keys})

    def client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self.handle))
