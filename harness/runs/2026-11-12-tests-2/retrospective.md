# Retrospective: the tests lens's second run, 2026-11-12

The second run of the tests lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)), over every spec and every module, after [the pilot](../2026-11-12-tests/retrospective.md). Every finding was verified (the pilot's decision 2, taken as a run parameter), and the fix stage put each survey's fixes on one branch.

## Outcome

| Stage | Result |
| :- | :- |
| Inventory | 107 requirements, 206 DoD items, 596 tests |
| Mutation | 924 survivors, 628 left to agents by the filter |
| Survey | 17 agents, one per spec and one per batch of modules: 172 findings |
| Verify | 172 verified: 157 confirmed, all as fixes, 15 refuted |
| Fix | 157 fixes on 17 branches, one per survey: 150 committed and accepted by their review, 4 found closed by an earlier fix on the same branch, 3 rejected by their review and dropped |
| Gate | 17 of 17 passed, the end-to-end tests included; 10 merged as #52 to #61 |
| Rebase | The other 7 conflicted with the 10; rebased by hand: 5 commits dropped and 4 cut as repeats of tests main had by then; gated again, merged as #62 to #68 |
| Merged | 145 tests, no code change |
| Sample | 12 of the 145 merged tests, drawn at random, judged by the operator: 12 wanted, none not worth it, none wrong (`sample.jsonl`) |
| Code | One defect: a validly signed token whose `azp` was present but not a string was accepted (REQ-002-PRS-NF001). Its fix was among the 3 rejected; fixed by hand, test first, on `fix/client-claim-not-a-string` |

## Cost

| Part | Agents | Subagent tokens | Time |
| :- | -: | -: | -: |
| Survey and verify | 190 | 10,272,000 | 38 min |
| Fix and review, first run (stopped at the spend limit) | 227 done, 48 failed | 11,689,000 | 58 min |
| Fix and review, resumed | 48 | 4,893,000 | 23 min |
| Duplicate check after the rebase | 7 | 444,000 | 5 min |
| All | 472 | 27,298,000 | |

Per merged test: about 188,000 tokens. Per 10 agents: 3.1 merged fixes, against the pilot's 2.4; the stopping threshold the pilot proposed (fewer than one per ten agents, two runs in a row) is far off.

## What went wrong, and what changes

| Problem | Effect | Change |
| :- | :- | :- |
| The survey workflow ran by its name, which gave the pilot's copy of the script | No mutant ids in the records, no merging of one key's findings; recovered from the evidence text by a script, which also picked up ids the evidence calls equivalent | Run a workflow by its file path (`scriptPath`); the fix stage did. The harness README says so for both workflows |
| The monthly spend limit was reached in the fix stage | 48 agents failed; every fix after a failed one in its branch failed too | Resumed with the same script and arguments: the finished agents replayed from cache. Nothing lost, since a branch only moves at a fix's last step |
| The workflow's worktrees stay after their agent | 67 worktrees after 30 minutes, 20 MB each | Removed while the run went on (unlocked worktrees whose branch moved past them), and the leftover `worktree-wf_*` branches after it. Not yet: the driver does this |
| A spec survey and a module survey add tests to the same file | 7 of 17 branches conflicted with the 10 merged first | Not yet: one branch per area (a spec's survey and its modules' surveys), so the tests of one file come from one branch |
| The rebase resolved conflicts by keeping both sides, by a script | Two files didn't parse, one test had two `parametrize` lines, one would have lost 91 lines of main's tests; found by the duplicate check, redone by hand | A conflict is resolved by hand or by an agent with the tests run after each one, never by a union merge |
| Spec and module surveys found the same gaps | 9 commits repeated a test main had by then, wholly or in part | The duplicate check: one read-only agent per rebased branch against main. With one branch per area, it moves into the fix stage |
| Mutation runs only the unit and integration tests | Several survivors are killed by the end-to-end tests; their verifiers found that and refuted them, at a verifier each | Not yet: a mutant the unit and integration tests leave goes through the end-to-end tests before it reaches a survey |
| The gate's output is buffered when redirected | No progress until it ended | Run with `PYTHONUNBUFFERED=1`; not yet in `gate.py` itself |
| Pushed with `git push`, not `gate.py --push` | `gates.jsonl` said `"pushed": false` until corrected by hand, as in the pilot | Not yet: `gate.py` pushes branches it passed earlier without running the checks again |

## What worked

- One branch per survey with its fixes in turn: 4 fixes found their gap closed by an earlier fix on the branch and committed nothing, instead of adding a repeat.
- The review caught the one code change that went too far (the `azp` fix also changed which client the rejection line names, without a test), and two smaller faults.
- Resume after the spend limit: 227 finished agents replayed from cache, only the 48 failed ones ran again.
- Every confirmed finding was within the specs: no proposal was needed.

## Decisions proposed

The pilot's six stand. In addition:

1. **One branch per area**, not per survey: a spec's survey and the surveys of its modules commit to one branch, so their tests don't conflict and repeats are found within the branch.
2. **End-to-end tests in the mutation step**, for the survivors of the unit and integration tests only.
3. **The driver** (the pilot's decision 4) cleans worktrees, pushes through the gate, and runs the duplicate check before the gate.

## For ADR-008

The operator judged a random sample of 12 merged tests against "would I have wanted this test" and rejected none, so ADR-008's first reconsideration trigger (more than one in five rejected) doesn't fire. Twelve with no rejection bounds the rejection rate at about 22 % with 95 % confidence; a larger sample after the next lens would narrow it.

The run kept to its Compliance: commits only on `auto/` branches (and the hand fix on its own branch), no spec, ADR or dependency changed, a failing test before every change, every verdict and review from another agent, every record schema-checked before triage (after the recovery above). The pilot's decisions 1 and 2 were applied here as run parameters; with them taken, ADR-008 can be accepted.
