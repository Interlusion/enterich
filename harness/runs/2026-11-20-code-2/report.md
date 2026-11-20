# Code lens: 2026-11-20-code-2

| Kind | Found | Confirmed |
| :- | -: | -: |
| lost-on-the-way | 2 | 2 |
| missed-pattern | 0 | 0 |
| rule-twice | 2 | 2 |
| wrong-outcome | 2 | 1 |
| all | 6 | 5 |

Suppressed: 0. Tracked in the backlog: 0.

## Ratchet (0)


## Fix (3)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `src/enterich/auth.py:Verifier._verify` | REQ-002-PRS-NF001 | If a token names a published key of a different key type than its allowed `alg` (for example `alg` RS256 with the `kid` of an EC key that has no `alg` member), PyJWT raises a TypeError that `_verify` doesn't catch. The token is still refused, but as an unexpected 500 with an `error` line instead of a 401 with a `rejection` line, so the refusal and its reason never reach the client or the log. | Test (tests/unit/test_auth.py): with FakeJwks(\[], extra_keys=\[ec_signer('key-ec').jwk() minus 'alg']) and settings() (RS256), `refusal(verifier(jwks), token(Signer('key-ec', rsa_signer().key, 'RS256')))` should be "algorithm not the key's". Today it raises TypeError. Fix: check the key family against the algorithm before decoding, for example by keeping in `SigningKey` the algorithms PyJWK supports for the key's kty/crv (or calling `jwt.get_algorithm_by_name(alg).prepare_key(key.key)` inside a try) and refusing with "algorithm not the key's". Or add `except (TypeError, ValueError): raise _Refused("algorithm not the key's")` around `jwt.decode`. Add an app-level test that the same token gets 401 and a `rejection` line. |
| `src/enterich/config.py:_Reader.as_published` | REQ-002-PRS-NF005 | If the SDK's AuthSettings rejects ENTERICH_ISSUER, the start-up problem names ENTERICH_RESOURCE_URL instead. The operator is sent to fix a variable that is fine, while the bad one is never named. | Test (tests/unit/test_config.py): load with ENTERICH_ISSUER='https://999.0.0.1/realms/x' should report a problem starting with 'ENTERICH_ISSUER:' and none for ENTERICH_RESOURCE_URL. Fix: validate each URL on its own, for example with `AnyHttpUrl` under the same `url_preserve_empty_path` config or a TypeAdapter for each field, and fail the variable whose value doesn't validate. Or read the field name from `ValidationError.errors()\[i]\['loc']` (issuer_url -> ISSUER, resource_server_url -> RESOURCE_URL) before you call `fail`. |
| `src/enterich/tools/__init__.py:_comment` | REQ-001-PRS-F015 | A comment call that ERPNext answers too late can say two different things. If the call's own 30 s timeout fires, the warning says flatly that the comment 'couldn't be added', even though ERPNext may have stored it. If the operation's deadline fires first, the same situation is reported, correctly, as 'it may be missing'. | Test: a fake ERPNext that stores the comment and then waits longer than CALL_TIMEOUT, with more than CALL_TIMEOUT left before the operation's deadline. The result's warning must say the comment may be missing, as it does when the deadline fires. Change: in `_comment`, word a timeout or transport failure of the comment call (an ErpnextError not of type Refused) as 'may be missing', and keep 'couldn't be added' for a Refused answer. |

## Proposal (2)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `src/enterich/tools/__init__.py:_written (unexpected-failure text)` | REQ-001-PRS-F015 | The text the agent gets for an unexpected failure is written twice: once as the UNEXPECTED constant and once as a near-copy inside _written's warning for a saved draft. Rewording one would leave the other behind. | Test: make an operation raise a RuntimeError after its insert. Assert that the result's last warning contains UNEXPECTED.rstrip('.'), not a literal. Change: in _written, set `failure = UNEXPECTED` (the existing `failure.rstrip('.')` already drops the final period). If the wording should differ only by 'its' or 'Enterich's', build both strings from one template. |
| `src/enterich/tools/invoicing.py:get_party (MAX_ADDRESSES)` | REQ-001-PRS-NF003 | The rule that a get cuts each of its tables to its first 100 rows is written a second time for a party's addresses as a separate MAX_ADDRESSES = 100. A change to shapes.MAX_ROWS / cut_rows would not reach get_customer and get_supplier. | Test: patch shapes.MAX_ROWS to 2, give the fake three linked addresses, and assert that get_customer returns 2 addresses with truncated \['addresses']. It fails today. Change: drop MAX_ADDRESSES and fetch `page_length=shapes.MAX_ROWS + 1`. Cut with `addresses, cut = cut_rows(addresses)` and set `"truncated": \["addresses"] if cut else \[]`, as get_item does for item_tax_templates. |
