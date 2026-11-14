# Tests lens: 2026-11-14-tests

| Kind | Found | Confirmed |
| :- | -: | -: |
| dod-gap | 0 | 0 |
| mutant-gap | 5 | 4 |
| weak-test | 0 | 0 |
| all | 5 | 4 |

Suppressed: 0. Tracked in the backlog: 0.

## Ratchet (1)

| Pattern | Findings | Means |
| :- | -: | :- |
| `limit-not-at-boundary` | 2 | A limit is tested well past its boundary, never at it and one beyond |

## Fix (4)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `src/enterich/app.py:_log_rejection` |  | The level of the `rejection` line is never asserted: written at info instead of warning, for every cause (401 without a token, 401 refused token, 403 missing scope, 503 no signing keys), no test notices, although the level of every other event is pinned by a test. | In tests/integration/test_service.py, add the line's level to the tuples already compared: `(r\["level"], r\["status"], r\["reason"]) == ("warning", 401, "no bearer token")` in test_missing_token_gets_401_with_the_metadata_pointer, and likewise "warning" in test_a_missing_scope_gets_403 and test_unreachable_jwks_gets_503_not_401 (and `first\["level"] == "warning"` in test_a_refused_token_gets_401_and_one_short_line_each). Any one of them is red on the mutant; all causes go through _log_rejection. |
| `src/enterich/app.py:create_app` |  | Nothing checks that create_app sets AuthSettings.validate_token_resource explicitly, as ADR-003 decides: set to None or left out, the SDK raises an MCPDeprecationWarning at every start (plain text on stderr) and Enterich relies on the SDK's changing default, and no test notices. | In tests/integration/test_service.py, a test that builds the app with warnings as errors, citing ADR-003: `with warnings.catch_warnings(): warnings.simplefilter("error"); create_app(settings(), jwks.client())` (optionally followed by one tools/list request with a valid token inside the same block). It passes on the original and raises MCPDeprecationWarning on both mutants. |
| `src/enterich/erpnext.py:_check_fields` | REQ-001-PRS-F018 | The refusal of a list that lacks exactly three fields is untested, so it can read "a, b, c and 0 more". | Add a test in tests/unit/test_erpnext.py: answer /api/resource/Item with {"data": \[{"name": "SKU-1"}]}, call get_list with fields name, item_code, item_group, stock_uom, and assert the text contains "(item_code, item_group, stock_uom): the agent user". Alternatively parametrize the existing exact-text test over three and four missing fields. |
| `src/enterich/erpnext.py:Erpnext._refusal` | REQ-001-PRS-F008 | The client's cut of a refusal is checked only as "at most 300", so a text of exactly 300 characters can lose its last character to "…" (mutmut_25) and a longer one can be cut to 299 (mutmut_29). | Add a test in tests/unit/test_erpnext.py using the `failure` helper: with prefix "ERPNext refused the request (417 ValidationError). ERPNext's message: ", a message that fills the text to exactly 300 characters comes back whole, and one character more comes back as the first 299 characters plus "…" (length 300). |

## Proposal (0)

