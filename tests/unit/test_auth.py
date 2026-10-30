"""REQ-002-PRS-NF001 (token check), REQ-002-PRS-NF007 (JWKS cache) and the
fetch limit of REQ-002-PRS-NF009."""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import anyio
import httpx2
import pytest
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from enterich.auth import JwksCache, KeysUnavailable, Verifier, last_refusal
from enterich.config import Settings
from tests.fakes.jwks import FakeJwks, Signer, claims, ec_signer, rsa_signer, token
from tests.fakes.settings import CLIENT_ID, JWKS_URL, RESOURCE_URL, SUBJECT, settings

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def verifier(jwks: FakeJwks, s: Settings | None = None, clock: Clock | None = None) -> Verifier:
    s = s or settings()
    return Verifier(s, JwksCache(s.jwks_url, jwks.client(), clock or Clock()))


async def refusal(v: Verifier, t: str) -> str:
    assert await v.verify_token(t) is None
    found = last_refusal.get()
    assert found is not None
    return found.reason


class Rel(int):
    """A time claim relative to when the test runs."""


# Time claims sit 10 s inside or outside this leeway, so a slow run (an
# emulated arm64 image takes minutes) doesn't move them across it.
LEEWAY = 30


def at_runtime(overrides: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    return {k: now + v if isinstance(v, Rel) else v for k, v in overrides.items()}


def b64(data: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


async def test_a_valid_token_is_accepted(jwks: FakeJwks, signer: Signer) -> None:
    access = await verifier(jwks).verify_token(token(signer))
    assert access is not None
    assert access.client_id == CLIENT_ID
    assert access.subject == SUBJECT
    assert access.scopes == ["openid", "profile"]
    assert access.resource == RESOURCE_URL
    assert access.claims == {
        "iss": "https://id.example.com/realms/example",
        "sid": "00000000-0000-0000-0000-0000000000aa",
    }


async def test_expires_at_carries_the_leeway(jwks: FakeJwks, signer: Signer) -> None:
    exp = int(time.time()) + 100
    access = await verifier(jwks).verify_token(token(signer, exp=exp))
    assert access is not None
    assert access.expires_at == exp + 5


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"iss": "https://id.example.com/realms/other"}, "wrong issuer"),
        ({"aud": "https://erp.example.com/other"}, "wrong audience"),
        ({"aud": "https://erp.example.com/mcp/"}, "wrong audience"),
        ({"azp": "another-client"}, "wrong client"),
        ({"sub": "00000000-0000-0000-0000-000000000002"}, "wrong subject"),
        ({"typ": "ID"}, "not an access token"),
        ({"typ": "Refresh"}, "not an access token"),
        ({"typ": None}, "not an access token"),
        ({"azp": None}, "wrong client"),
        ({"azp": CLIENT_ID, "client_id": "another-client"}, "azp and client_id differ"),
        ({"exp": Rel(-LEEWAY - 10)}, "expired"),
        ({"nbf": Rel(LEEWAY + 10)}, "not yet valid"),
        ({"iat": Rel(LEEWAY + 10)}, "not yet valid"),
        ({"sub": None}, "missing claim"),
        ({"iat": None}, "missing claim"),
        ({"exp": None}, "missing claim"),
    ],
)
async def test_tokens_are_refused(
    jwks: FakeJwks, signer: Signer, overrides: dict[str, Any], reason: str
) -> None:
    v = verifier(jwks, settings(clock_leeway=str(LEEWAY)))
    assert await refusal(v, token(signer, **at_runtime(overrides))) == reason


async def test_signature_valid_refusals_carry_subject_and_client(
    jwks: FakeJwks, signer: Signer
) -> None:
    v = verifier(jwks)
    await v.verify_token(token(signer, sub="person"))
    found = last_refusal.get()
    assert found is not None
    assert (found.subject, found.client) == ("person", CLIENT_ID)


async def test_signature_invalid_refusals_carry_nothing_unsigned(jwks: FakeJwks) -> None:
    stranger = rsa_signer("key-1", key=1)  # same kid, another key
    v = verifier(jwks)
    assert await refusal(v, token(stranger, sub="person")) == "bad signature"
    found = last_refusal.get()
    assert found is not None
    assert (found.subject, found.client) == (None, None)


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": Rel(-LEEWAY + 10)},
        {"nbf": Rel(LEEWAY - 10)},
        {"iat": Rel(LEEWAY - 10)},
    ],
)
async def test_times_within_the_leeway_are_accepted(
    jwks: FakeJwks, signer: Signer, overrides: dict[str, Any]
) -> None:
    v = verifier(jwks, settings(clock_leeway=str(LEEWAY)))
    assert await v.verify_token(token(signer, **at_runtime(overrides))) is not None


@pytest.mark.parametrize("typ", ["at+jwt", "application/at+jwt", "AT+JWT"])
async def test_the_header_typ_marks_an_access_token(
    jwks: FakeJwks, signer: Signer, typ: str
) -> None:
    assert await verifier(jwks).verify_token(token(signer, {"typ": typ}, typ=None)) is not None


@pytest.mark.parametrize("claim", ["ID", "Refresh"])
async def test_a_claim_typ_other_than_bearer_is_refused_even_with_the_header(
    jwks: FakeJwks, signer: Signer, claim: str
) -> None:
    t = token(signer, {"typ": "at+jwt"}, typ=claim)
    assert await refusal(verifier(jwks), t) == "not an access token"


async def test_a_key_without_alg_verifies_every_configured_algorithm(signer: Signer) -> None:
    ps = Signer("key-ps", signer.key, "PS256")
    no_alg = {k: v for k, v in ps.jwk().items() if k != "alg"}
    jwks = FakeJwks([], extra_keys=[no_alg])
    s = settings(token_algorithms="RS256,PS256")
    assert await verifier(jwks, s).verify_token(token(ps)) is not None


async def test_a_key_is_used_only_with_the_algorithm_it_names(signer: Signer) -> None:
    named = {**signer.jwk(), "alg": "RS256"}
    jwks = FakeJwks([], extra_keys=[named])
    s = settings(token_algorithms="RS256,PS256")
    other_alg = Signer(signer.kid, signer.key, "PS256")
    assert await refusal(verifier(jwks, s), token(other_alg)) == "algorithm not the key's"


async def test_client_id_counts_when_azp_is_absent(jwks: FakeJwks, signer: Signer) -> None:
    t = token(signer, azp=None, client_id=CLIENT_ID)
    assert await verifier(jwks).verify_token(t) is not None


async def test_alg_none_is_refused(jwks: FakeJwks, signer: Signer) -> None:
    t = f"{b64({'alg': 'none', 'kid': signer.kid})}.{b64({'sub': SUBJECT})}."
    assert await refusal(verifier(jwks), t) == "algorithm not allowed"


async def test_hs256_keyed_with_the_public_key_is_refused(jwks: FakeJwks, signer: Signer) -> None:
    pem = signer.key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    signing_input = f"{b64({'alg': 'HS256', 'kid': signer.kid})}.{b64(claims())}"
    mac = hmac.new(pem, signing_input.encode(), hashlib.sha256).digest()
    t = f"{signing_input}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"
    assert await refusal(verifier(jwks), t) == "algorithm not allowed"


async def test_an_algorithm_outside_the_configured_list_is_refused(jwks: FakeJwks) -> None:
    ec = ec_signer()
    jwks.signers.append(ec)
    assert await refusal(verifier(jwks), token(ec)) == "algorithm not allowed"
    s = settings(token_algorithms="RS256,ES256")
    assert await verifier(jwks, s).verify_token(token(ec)) is not None


async def test_unknown_kid_is_refused(jwks: FakeJwks) -> None:
    other = rsa_signer("key-2", key=1)
    assert await refusal(verifier(jwks), token(other)) == "unknown key"


async def test_a_kid_with_a_newline_is_refused(jwks: FakeJwks) -> None:
    other = rsa_signer('x"\n{"event":"start"}', key=1)
    assert await refusal(verifier(jwks), token(other)) == "unknown key"


@pytest.mark.parametrize("t", ["", "garbage", "a.b.c", "a.b"])
async def test_a_non_jwt_is_refused(jwks: FakeJwks, t: str) -> None:
    assert await refusal(verifier(jwks), t) == "not a JWT"


async def test_a_9_kib_token_is_refused(jwks: FakeJwks, signer: Signer) -> None:
    t = token(signer, padding="x" * 9 * 1024)
    assert await refusal(verifier(jwks), t) == "token too long"


async def test_a_jku_header_causes_no_fetch(jwks: FakeJwks, signer: Signer) -> None:
    v = verifier(jwks)
    await v.verify_token(token(signer, {"jku": "https://attacker.example.net/keys"}))
    assert jwks.requested == [JWKS_URL]


async def test_an_embedded_jwk_header_is_not_used(jwks: FakeJwks) -> None:
    attacker = rsa_signer("key-1", key=1)
    t = token(attacker, {"jwk": attacker.jwk()})
    assert await refusal(verifier(jwks), t) == "bad signature"


async def test_encryption_keys_in_the_jwks_are_ignored(signer: Signer) -> None:
    oaep = {**rsa_signer("enc-1", key=1).jwk(), "use": "enc", "alg": "RSA-OAEP"}
    jwks = FakeJwks([signer], extra_keys=[oaep])
    assert await verifier(jwks).verify_token(token(signer)) is not None


async def test_a_key_marked_for_encryption_never_verifies_a_token(signer: Signer) -> None:
    encryption = rsa_signer("enc-2", key=1)
    jwks = FakeJwks([signer], extra_keys=[{**encryption.jwk(), "use": "enc"}])
    assert await refusal(verifier(jwks), token(encryption)) == "unknown key"


async def test_jwks_is_cached_for_5_minutes(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    for _ in range(3):
        assert await v.verify_token(token(signer)) is not None
    assert jwks.fetches == 1
    clock.now += 299
    await v.verify_token(token(signer))
    assert jwks.fetches == 1
    clock.now += 2
    await v.verify_token(token(signer))
    assert jwks.fetches == 2


async def test_a_removed_key_stops_working_within_5_minutes(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    assert await v.verify_token(token(signer)) is not None
    jwks.signers[:] = [rsa_signer("key-2", key=1)]  # rotated: key-1 removed, key-2 added
    clock.now += 301
    assert await refusal(v, token(signer)) == "unknown key"


async def test_unknown_kids_refetch_at_most_once_in_30_s(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    await v.verify_token(token(signer))
    assert jwks.fetches == 1
    clock.now += 31
    for i in range(5):
        await v.verify_token(token(rsa_signer(f"unknown-{i}", key=1)))
    assert jwks.fetches == 2


async def test_a_new_key_is_found_by_its_kid(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    await v.verify_token(token(signer))
    rotated = rsa_signer("key-2", key=1)
    jwks.signers.append(rotated)
    clock.now += 31
    assert await v.verify_token(token(rotated)) is not None


async def test_unreachable_jwks_without_keys_raises(jwks: FakeJwks, signer: Signer) -> None:
    jwks.down = True
    with pytest.raises(KeysUnavailable):
        await verifier(jwks).verify_token(token(signer))


async def test_cached_keys_work_until_5_minutes_then_503(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    assert await v.verify_token(token(signer)) is not None
    jwks.down = True
    clock.now += 299
    assert await v.verify_token(token(signer)) is not None
    clock.now += 2
    with pytest.raises(KeysUnavailable):
        await v.verify_token(token(signer))


@pytest.mark.parametrize("keys", [[], [{"kty": "RSA", "kid": "broken", "n": "x", "e": "AQAB"}]])
async def test_a_jwks_without_usable_keys_counts_as_unavailable(
    signer: Signer, keys: list[dict[str, Any]]
) -> None:
    jwks = FakeJwks([], extra_keys=keys)
    with pytest.raises(KeysUnavailable):
        await verifier(jwks).verify_token(token(signer))


async def test_an_empty_refresh_keeps_the_known_keys(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    v = verifier(jwks, clock=clock)
    assert await v.verify_token(token(signer)) is not None
    saved = list(jwks.signers)
    jwks.signers.clear()
    clock.now += 31
    await v.verify_token(token(rsa_signer("unknown", key=1)))
    jwks.signers.extend(saved)
    assert await v.verify_token(token(signer)) is not None


async def test_a_slow_fetch_doesnt_hold_up_known_keys(signer: Signer) -> None:
    release = anyio.Event()
    fetches = 0

    async def handle(request: httpx2.Request) -> httpx2.Response:
        nonlocal fetches
        fetches += 1
        if fetches > 1:
            await release.wait()
        return httpx2.Response(200, json={"keys": [signer.jwk()]})

    clock = Clock()
    s = settings()
    v = Verifier(
        s, JwksCache(s.jwks_url, httpx2.AsyncClient(transport=httpx2.MockTransport(handle)), clock)
    )
    assert await v.verify_token(token(signer)) is not None
    clock.now += 31
    async with anyio.create_task_group() as tg:
        tg.start_soon(v.verify_token, token(rsa_signer("unknown", key=1)))
        await anyio.sleep(0.05)
        with anyio.fail_after(1):
            assert await v.verify_token(token(signer)) is not None
        release.set()


async def test_an_outage_is_retried_at_most_every_30_s(jwks: FakeJwks, signer: Signer) -> None:
    clock = Clock()
    jwks.down = True
    v = verifier(jwks, clock=clock)
    for _ in range(5):
        with pytest.raises(KeysUnavailable):
            await v.verify_token(token(signer))
    assert jwks.fetches == 1
    jwks.down = False
    clock.now += 30
    assert await v.verify_token(token(signer)) is not None
    assert jwks.fetches == 2
