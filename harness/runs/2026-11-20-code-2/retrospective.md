# Retrospective: the code lens's second and third runs, 2026-11-20

The code lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)) ran twice more over all nine records after its [first run](../2026-11-19-code/retrospective.md): the second run (`2026-11-20-code`) after the first run's fixes, and the third run (here) after the second's and after the fix stage's review began to check where else a fixed mechanism runs (#110).

## Outcome

| Run | Found | Confirmed | Fixes | Proposals | Fix stage | By hand |
| :- | -: | -: | -: | -: | :- | :- |
| 1 | 15 | 13 | 5 | 8 | 5 accepted | the proposals and the reviews' gaps |
| 2 | 8 | 6 | 2 | 4 | 1 accepted, 1 rejected | the rejected fix and the proposals |
| 3 | 6 | 5 | 3 | 2 | 2 accepted, 1 rejected | the rejected fix and the proposals |

- **Third run's fixes:** a token for a key of another type than its algorithm gave a 500 instead of a 401; a bad `ENTERICH_ISSUER` was reported as `ENTERICH_RESOURCE_URL`; a comment ERPNext answered too late was reported as not added.
- **Third run's proposals:** `MAX_ADDRESSES` beside `shapes.MAX_ROWS`; a near-copy of `UNEXPECTED` in `_written`.
- **Rejected by the new check:** the config fix named the issuer, but only when both URLs passed the URL rules; with the other one wrong, neither was checked against the metadata. The review found it by trying another place the mechanism runs, as #110 asks. Fixed by hand: each URL is checked on its own.
- **Refuted twice:** an update whose answer is lost says only "didn't answer". Both verifiers held it within REQ-001-PRS-F015 as written, so it is a spec question, now in the backlog.
- No finding of an earlier run came back, so the earlier fixes held.
- **One branch by hand:** the gate passed and pushed `auto/code-integration-order-to-cash-drafts` and held `auto/code-unit-auth` back for its CHANGELOG line. Rather than three pull requests in turn, each rebased and reviewed again, the accepted commits, the fixes by hand and these records went on one branch, `fix/code-lens-third-run`, checked by hand with the gate's checks, the end-to-end tests included. So `gates.jsonl` names branches that weren't merged as such.

## Cost

| Run | Agents | Tokens | Per confirmed finding |
| :- | -: | -: | -: |
| 1 | 24 | 1.52M | 117k |
| 2 | 17 | 1.28M | 214k |
| 3 | 15 | 1.20M | 241k |

The third run's fix stage: 6 agents, 0.34M tokens.

## What changes

- **The rest is judged by what the fixes are, not by their count.** The bar set before the third run was about 2 fixes or fewer. The run had 3, but they were edge cases of an unusual authorization server, a mistyped variable and a warning's wording, where the first run's were wrong outcomes for the agent (payments refused, warnings lost, duplicates missed). The lens rests now, until a Python file of `src/` changes, without a fourth run.
- **A survey is a sample, not a sweep.** The three full runs found different things over the same code, so the first retrospective's "rests after one short `--since` run" didn't hold: a further run of the same records still finds something. Resting is a choice by cost and kind of finding, not a proof that nothing is left.
- **The class check pays.** The first fix stage with it rejected one fix of three, and the gap it named was the kind the reviews by hand had found after the first run.
- **Commit hashes in the records look like keys to gitleaks** when a commit's subject says "key" just before the next hash in `outcomes.jsonl`, as the auth fix's did. `record.py`'s scan didn't see it, as the workflow's output puts each hash on a line of its own. `.gitleaks.toml` now lets a 40-hex hash through under `harness/runs/` only.
- **A finding refuted twice goes to the backlog** as a spec question rather than to the next run.
