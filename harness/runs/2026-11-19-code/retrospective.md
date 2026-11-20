# Retrospective: the code lens's first run, 2026-11-19

The first run of the code lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)) over all nine records of `harness/modules.jsonl`, with its four concerns: what a path loses, a wrong outcome after a side effect, a rule written twice, and a pattern one place misses.

## Outcome

| Stage | Result |
| :- | :- |
| Survey | 9 agents: 15 findings |
| Verify | 15 verified, 13 confirmed, 2 refuted |
| Triage | 5 to fix, 8 proposals; nothing suppressed |
| Fix | 3 `auto/` branches, 5 fixes, all accepted by their reviews and passed by the gate (#100, #101, #102) |
| By hand | the 8 proposals, the 2 refuted findings and what the reviews of the branches found (#103, #105) |

| Kind | Found | Confirmed |
| :- | -: | -: |
| lost-on-the-way | 4 | 4 |
| missed-pattern | 4 | 2 |
| rule-twice | 7 | 7 |
| wrong-outcome | 0 | 0 |

- **Fixes:** a failed JWKS fetch logged only its exception's class; a payment's references and party in another letter case were refused as unknown or as another party's; a draft saved before its result failed lost its duplicate warning; a repeated invoice draft with an item code in another case went through.
- **Proposals:** the journal duplicate check's silent bound of 1,000 rows; seven rules written twice, each a limit or a list typed into a message or a description beside its constant.
- **Refuted, then fixed:** the journal duplicate check's accounts and the returns' item codes compared without folding case. Both were refuted because the verifier held them against the code's pattern, which had one caller, not against a rule; the rule came with the fixes (REQ-001-PRS-F027), and under it both were real (#103, #105).

## What the reviews by hand found

Every branch the gate passed got further commits before its merge:

- **#101:** REQ-001-PRS-F027, the rule the fix implied, and a test for an invoice given twice in two letter cases.
- **#102:** the spec lines for REQ-001-PRS-F015 and the item codes. The fix changed nine write paths, but its test covered one; its review named that and accepted it.
- **#103:** names compare as ERPNext's database does, accents included, measured against MariaDB; returns follow it; every write keeps its duplicate warning, tested.
- **#105:** at the bound, the last draft read could be cut off and taken for a duplicate (ERPNext counts `page_length` in joined child rows). The run's finding asked for a warning at the bound and didn't see this.

The fix stage's commits held, but each needed its spec line by hand (ADR-008 keeps specs to the operator), and most fixes covered fewer paths than their class.

## Cost

| Workflow | Agents | Tokens |
| :- | -: | -: |
| Survey and verify | 24 | 1.52M |
| Fix and review | 10 | 0.56M |
| Reviews again after the rebases | 4 | 0.19M |
| All | 38 | 2.27M |

About 117,000 tokens a confirmed finding for survey and verify, 175,000 with the fix stage. The two branches held back by the CHANGELOG cost the rebased reviews.

## What changes

- **No `refactor:` path for the gate.** The seven rules written twice took one `refactor:` commit and one `test:` commit by hand. The three limits in messages did have a red test (the message follows the limit as patched), so they could have gone through the gate as fixes; the four in descriptions and constants have no red test, and their only proof is the tool-list snapshot, which the gate may not change and which a pure restructure leaves as it is anyway. A path of its own, for so few changes a run and a lens that rests, would cost more to build and trust than doing them by hand. Restructures stay by hand from the report.
- **Dropped findings are checked again** when the run's fixes add or change a rule: both refuted findings were real under F027. For analysis 003.
- **The CHANGELOG serialises the code branches:** every branch adds a line, so the gate held two of three back until the first was merged. For analysis 003.
- **A fix covers its class:** the reviews by hand found the same gap beside each fix more often than a new one. The fix stage's review should ask where else the fixed mechanism runs, not only whether the test shows the finding.
- **The lens rests** after one short `--since` run on main, until a Python file of `src/` changes.
