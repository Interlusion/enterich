# Tests lens: 2026-11-12-tests

| Kind | Found | Confirmed |
| :- | -: | -: |
| dod-gap | 4 | 2 |
| mutant-gap | 4 | 3 |
| weak-test | 0 | 0 |
| all | 8 | 5 |

Suppressed: 0. Confirmed but named in the backlog: 1.

## Fix (5)

| Location | Requirement | Claim | Proposal |
| :- | :- | :- | :- |
| `req-001-core.md#REQ-001-PRS-F006 item 2` | REQ-001-PRS-F006 | The only automated check that no ERPNext call uses a side door is the fake's `_door` detector, which the integration fixture runs on every call. No test shows the detector actually flags a door, so a broken detector would let the whole suite pass. Also, no test checks across all tools that no input schema has a DocType, report, method, field-list, filter or path property; only list_items is tried with `doctype` and `fields`. | Add a unit test that feeds `_door` one request per door and asserts it names each one: DELETE, a body with docstatus 1, `amended_from`, a nested `doc` string with docstatus 2, the `run_method` parameter, every DOOR_METHODS entry on v1, v2 and v2-document method routes, and savedocs with action Submit. In the same test, assert it returns None for a resource path or parameter value such as `X?run_method=discard`. Also add a test that walks every tool's inputSchema and fails on any property named or titled doctype, report, method, fields, filters or path. |
| `req-001-core.md#REQ-001-PRS-F020 item 3` | REQ-001-PRS-F020 | For purchase invoices, only the create without a template is tested. No test shows that a purchase create with a template given, an update clearing the template, an update of only the remarks, or an update giving a template behaves as the sales side does. | Parametrise, or copy for purchase invoices, the three sales tests named above: with `erp.item_taxes['PAPER']` set, a create giving a purchase template has no warning; an update with `taxes_and_charges=''` and an update of only `remarks` return the item-tax warning; an update giving a template returns none. |
| `src/enterich/shapes.py:page` | REQ-001-PRS-F014 | No test covers a page that returns exactly `limit` records with none beyond, so `has_more` being true at len(records) == limit goes unnoticed. | Unit test: page([{...}, {...}], offset=0, limit=2)["has_more"] is False, and with three records it is True. Or an integration list with exactly `limit` matching records asserts has_more False. |
| `src/enterich/tools/__init__.py:_log` | REQ-002-PRS-NF008 | The DoD item on durations (a 1 s delayed fake, 3 calls, ERPNext duration of at least 3 s within the total) has no test. The only assertion is `duration >= erpnext_duration >= 0`, so integer rounding, a constant 3 or a total of monotonic()+started all pass. | Integration test: erp.delay = 0.25 on a create making three ERPNext calls. Assert erpnext_calls == 3, 0.75 <= erpnext_duration <= duration, and duration < 0.75 + 2 (an upper bound). The fractional delay kills the integer-rounding mutants, since the values would come out 0 or 1. |
| `src/enterich/tools/__init__.py:get_document` | REQ-001-PRS-F014 | No test checks that a get returns yes/no fields as JSON booleans, so dropping `flags` (is_return returned as 0/1) passes, because the dict-equality asserts treat 0 == False. | In the get_sales_invoice / get_purchase_invoice integration tests, assert `result["is_return"] is False` (and `is True` for a return invoice whose fake has is_return=1), or compare the raw result text for `"is_return": false`. |

## Proposal (0)

