"""The token check of ADR-003 (REQ-002-PRS-NF001) and the JWKS cache.

A refused token returns None, so the SDK answers 401. Why it was refused is
kept in `last_refusal` for the rejection log line the app writes from the
response status. With no usable signing keys, the verifier raises
`KeysUnavailable`, which the app answers with 503.
"""

import json
import logging
import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast

import anyio
import httpx2
import jwt
from jwt import PyJWK
from mcp.server.auth.provider import AccessToken

from erpel import log
from erpel.config import Settings

MAX_TOKEN_LENGTH = 8 * 1024
MAX_JWKS_BYTES = 1024 * 1024
JWKS_TTL = 300.0
JWKS_RETRY_INTERVAL = 30.0
ACCESS_TOKEN_TYPES = frozenset({"at+jwt", "application/at+jwt"})


@dataclass(frozen=True)
class SigningKey:
    key: Any  # a cryptography public key
    alg: str | None  # the JWK's own `alg`, if it names one


@dataclass(frozen=True)
class Refusal:
    reason: str
    subject: str | None = None
    client: str | None = None


last_refusal: ContextVar[Refusal | None] = ContextVar("last_refusal", default=None)


class KeysUnavailable(Exception):  # noqa: N818 - a state, not an error of the request
    """No signing keys can be used: the cache is empty or expired and a fetch failed."""


class JwksCache:
    """Keys from the configured JWKS URL only, cached for 5 minutes.

    An unknown `kid` refetches at most once per 30 s, and a failed fetch is
    retried after 30 s at the earliest, so neither attackers nor an outage
    turn requests into JWKS fetches.
    """

    def __init__(
        self,
        url: str,
        client: httpx2.AsyncClient,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._url = url
        self._client = client
        self._clock = clock
        self._keys: dict[str, SigningKey] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None
        self._lock = anyio.Lock()

    async def key(self, kid: str) -> SigningKey | None:
        """The key for `kid`, or None if it isn't published; raises `KeysUnavailable`."""
        known = self._keys.get(kid)
        if known is not None and self._fresh():
            return known  # no waiting for a fetch another request started
        async with self._lock:
            if not self._fresh():
                await self._refresh()
                if not self._fresh():
                    raise KeysUnavailable
            elif kid not in self._keys:
                await self._refresh()
            return self._keys.get(kid)

    def _fresh(self) -> bool:
        return self._fetched_at is not None and self._clock() - self._fetched_at < JWKS_TTL

    def _may_attempt(self) -> bool:
        return (
            self._last_attempt is None or self._clock() - self._last_attempt >= JWKS_RETRY_INTERVAL
        )

    async def _refresh(self) -> None:
        if not self._may_attempt():
            return
        self._last_attempt = self._clock()
        try:
            keys = await self._fetch()
        except (httpx2.HTTPError, ValueError, _JwksError) as exc:
            log.event("jwks", logging.WARNING, outcome="failed", reason=type(exc).__name__, keys=0)
            return
        self._keys = keys
        self._fetched_at = self._clock()
        log.event("jwks", outcome="fetched", keys=len(keys))

    async def _fetch(self) -> dict[str, SigningKey]:
        async with self._client.stream("GET", self._url) as response:
            if response.status_code != 200:
                raise _JwksError(f"status {response.status_code}")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) > MAX_JWKS_BYTES:
                    raise _JwksError("too large")
        data: object = json.loads(body)
        listed = data.get("keys") if isinstance(data, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
        if not isinstance(listed, list):
            raise _JwksError("no keys")
        signing: list[dict[str, Any]] = [
            cast("dict[str, Any]", k)
            for k in cast("list[object]", listed)
            if isinstance(k, dict)
            and k.get("use", "sig") == "sig"  # pyright: ignore[reportUnknownMemberType]
            and isinstance(k.get("kid"), str)  # pyright: ignore[reportUnknownMemberType]
        ]
        keys: dict[str, SigningKey] = {}
        for jwk in signing:
            try:
                parsed = PyJWK(jwk)  # pyright: ignore[reportArgumentType] - JWKDict is a dict
            except jwt.PyJWTError:
                continue  # a key PyJWT can't use for signatures
            alg = jwk.get("alg")
            keys[jwk["kid"]] = SigningKey(parsed.key, alg if isinstance(alg, str) else None)
        if not keys:
            # Counts as a failed fetch: the cached keys stay, and without any, 503.
            raise _JwksError("no usable signing keys")
        return keys


class Verifier:
    """The SDK's `TokenVerifier`: one issuer, one audience, one client, one subject."""

    def __init__(self, settings: Settings, keys: JwksCache) -> None:
        self._settings = settings
        self._keys = keys

    async def verify_token(self, token: str) -> AccessToken | None:
        last_refusal.set(None)
        try:
            return await self._verify(token)
        except _Refused as refused:
            last_refusal.set(refused.refusal)
            return None

    async def _verify(self, token: str) -> AccessToken:
        s = self._settings
        if len(token) > MAX_TOKEN_LENGTH:
            raise _Refused("token too long")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError:
            raise _Refused("not a JWT") from None
        alg = header.get("alg")
        if alg not in s.token_algorithms:
            raise _Refused("algorithm not allowed")
        kid = header.get("kid")
        if not isinstance(kid, str):
            raise _Refused("no key ID")
        key = await self._keys.key(kid)
        if key is None:
            raise _Refused("unknown key")
        if key.alg is not None and key.alg != alg:
            raise _Refused("algorithm not the key's")

        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=[alg],
                audience=s.resource_url,
                issuer=s.issuer,
                leeway=s.clock_leeway,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError:
            raise _Refused("expired") from None
        except jwt.ImmatureSignatureError:
            raise _Refused("not yet valid") from None
        except jwt.InvalidAudienceError:
            raise _Refused("wrong audience") from None
        except jwt.InvalidIssuerError:
            raise _Refused("wrong issuer") from None
        except jwt.InvalidSignatureError:
            raise _Refused("bad signature") from None
        except jwt.MissingRequiredClaimError:
            raise _Refused("missing claim") from None
        except jwt.PyJWTError:
            raise _Refused("invalid token") from None

        # The signature is valid from here on, so subject and client may be logged.
        subject = _str_claim(claims, "sub")
        azp = _str_claim(claims, "azp")
        client_id = _str_claim(claims, "client_id")
        client = azp if azp is not None else client_id

        def refuse(reason: str) -> _Refused:
            return _Refused(reason, subject, client)

        if azp is not None and client_id is not None and azp != client_id:
            raise refuse("azp and client_id differ")
        if client is None or client != s.client_id:
            raise refuse("wrong client")
        if subject != s.subject:
            raise refuse("wrong subject")
        typ = header.get("typ")
        header_marks = isinstance(typ, str) and typ.lower() in ACCESS_TOKEN_TYPES
        claim_typ = claims.get("typ")
        if claim_typ is not None and claim_typ != "Bearer":
            raise refuse("not an access token")  # an ID or refresh token, whatever the header
        if not header_marks and claim_typ != "Bearer":
            raise refuse("not an access token")

        scope = claims.get("scope")
        sid = _str_claim(claims, "sid")
        return AccessToken(
            token=token,
            client_id=client,
            scopes=scope.split() if isinstance(scope, str) else [],
            # The SDK refuses a token once expires_at has passed, without leeway of its own.
            expires_at=int(claims["exp"]) + s.clock_leeway,
            resource=s.resource_url,
            subject=subject,
            claims={"iss": s.issuer, "sid": sid},
        )


class _JwksError(Exception):
    """The JWKS response can't be used."""


class _Refused(Exception):  # noqa: N818 - control flow inside the verifier
    def __init__(self, reason: str, subject: str | None = None, client: str | None = None) -> None:
        super().__init__(reason)
        self.refusal = Refusal(reason, subject, client)


def _str_claim(claims: dict[str, Any], name: str) -> str | None:
    value = claims.get(name)
    return value if isinstance(value, str) else None
