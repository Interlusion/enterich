# Retrospective: the docs lens's first run, 2026-11-17

The first run of the docs lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)) over all eight surveyed records of `harness/documents.jsonl`, the day after the lens's deterministic checks (`tests/repo/test_docs.py`) went into CI.

## Outcome

| Stage | Result |
| :- | :- |
| Survey | 8 agents: 11 findings; the README, the configuration guide, the Keycloak guide and the drafts guides none |
| Verify | 11 verified, 11 confirmed |
| Triage | 8 to fix, 3 proposals; nothing suppressed |
| Fix | by hand, no fix workflow: 4 tool descriptions, 5 places in the arc42 document, 3 sentences in the specs |

| Record | Confirmed |
| :- | -: |
| tool-descriptions | 3 |
| architecture | 5 |
| core-specs | 2 |
| area-specs | 1 |

- **Tool descriptions:** the invoice creates said `posting_date` defaults to today, where a draft without it gets the day of each save, so a later update moves it and its due date; `get_item` said the company's accounts, where it gives the item's own defaults; `create_draft_payment_entry` said every unallocated amount is named in `warnings`, where a payment without references gets none.
- **Architecture:** the name lookup at a counted create, the drafts limit across replicas (QS-23 and the deployment view), the return methods in the context table, the order of the tax template read and the duplicate check, the `returns` module.
- **Specs, where the code was right:** `status` only where a DocType has one, the tax template's `frappe.client.get` and its company check (REQ-001-PRS-F007, whose test was there), and `on_hold` in REQ-007's calls table.

No finding needed a change to the code.

## Cost

| Workflow | Agents | Tokens |
| :- | -: | -: |
| Survey and verify | 19 | 1.49M |

About 135,000 tokens a confirmed finding. Four of the eight surveys found nothing.

## What changes

- **Few findings, all real:** the deterministic checks and the earlier lenses' reading had left little, and what was left was where no check reads: descriptions of behaviour that changed after they were written. The drifts that mattered most were in the tool descriptions, the text the agent model reads.
- **The lens rests** until a document or what it is read against changes, and then runs with `--since` on the records touched. A full run isn't worth its cost again.
- **Document fixes stay by hand:** eleven sentences took less than a fix workflow would. Whether the fix stage should take them waits for a run with more.
