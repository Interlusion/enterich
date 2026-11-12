# Retrospective: the tests lens's pilot, 2026-11-12

The first run of the improvement pipeline ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)), on a slice: REQ-001's Definition of Done, and the mutation survivors of `enterich.shapes` and `enterich.tools`. ADR-008's Compliance asks for this retrospective before a second lens; its decisions below are proposals until the operator takes them.

## Outcome

| Stage | Result |
| :- | :- |
| Inventory | 107 requirements, 206 DoD items of 71 PRS, 588 tests; 1 PRS without a test citing it, 63 cited only by section or module |
| Mutation | 7,096 mutants over `src/enterich/`: 6,154 killed, 934 survived, 8 timeouts; the filter judged 296 survivors (message text, `cast()` type text) |
| Survey | 2 agents, 24 findings |
| Verify | 8 verified (the cap of 4 per survey): 5 confirmed, 3 refuted; 16 left unverified in `unverified.jsonl` |
| Fix | 5 branches, each one `test:` commit, each shown red and reviewed by a second agent; no code change was needed |
| Gate | 5 of 5 passed, the end-to-end tests included; merged as #47 to #51 |
| Ratchet | The 8 mutants the fixes named are killed on `main` (`mutmut run` on them after the merge) |

The most consequential finding: the fake ERPNext's side-door detector, which every integration test relies on to prove REQ-001-PRS-F006, was never tested itself; with it switched off, the suite passed. Now 51 tests fail.

The refutations held up: each named the test or shared code path that already covers the claim.

## Cost

| Run | Agents | Subagent tokens | Time |
| :- | -: | -: | -: |
| Survey and verify | 10 | 646,000 | 8.6 min |
| Fix and review, 4 fixes | 9 | 498,000 | 9.2 min |
| Fix and review, the 5th | 2 | 91,000 | 2.4 min |
| All | 21 | 1,235,000 | |

Two fix runs were stopped early and are not counted: one for a wrong argument, one for a full disk. The mutation run is CPU only: about 31 minutes on 8 cores, and mutmut reruns only what changed.

Per confirmed and merged fix: about 250,000 tokens. Survey and verify were 52 % of it, fix and review 48 %.

## What went wrong, and what changed

| Problem | Effect | Changed |
| :- | :- | :- |
| The harness's own tests cite requirement IDs as data | The inventory counted them as covering requirements | The inventory leaves out `tests/repo/test_harness.py` |
| A finding's key was its kind and location | 3 locations held 2 findings each; a suppression would hit both | A mutant gap's key is its lowest mutant id; triage refuses two records with one key; the workflow merges a survey's findings with one key |
| "Named in the backlog" was a text search for the requirement ID | An archived item and an unrelated one counted | A suppression names its backlog item; it counts while the item is open |
| The session copied 16 KB of records into the workflow's arguments by hand | One fix got another's mutant diff; the run was stopped | The arguments are keys and slugs; each agent reads its record from the committed `fixes.jsonl` |
| The disk was full | Found only when the database container failed; the run was stopped | Not yet: a free-space check before agents start |
| Workflow agents see the operator's latest message | A run started in the turn after "vm-cleanup": one agent refused, as it should have | Not yet: start a workflow only in the turn of the operator's go |
| The gate can't tell the end-to-end tests ran | It refuses without `E2E_ERPNEXT_URL`, but a skipped test passes | Not yet: the gate checks that `tests/e2e` ran, not skipped |
| The branches were pushed with `git push` after the gate, not `gate.py --push` | `gates.jsonl` said `"pushed": false` | Corrected by hand in this run |
| CI checks all Markdown | Triage's report failed mdformat | `harness/runs/` is excluded from mdformat |

## What worked

- One agent per item with a fixed schema: no finding was malformed, and every reason named files and lines.
- Verify by another agent, defaulting to refuted: 3 of 8 refuted, each with evidence.
- Red first, against the mutant or a break the agent chose: the fix agents tried 13 breaks of the side-door detector, not only the one in the finding.
- The review agent found real but minor points (two detector mutants still surviving, a tight time bound) and accepted, which matched the gate.
- Branches from `main`, independent of the pipeline's branch: five small PRs, merged in any order.

## Decisions proposed

1. **Stopping.** A lens stops on a scope when two runs in a row confirm fewer than one fix per ten agents (the pilot: 5 fixes, 21 agents, so one per four). Before that, a run stops on what ADR-008 names: the universe done, the agent budget spent, or a survey with no new keys.
2. **Verify everything a survey finds**, with no cap: the cap left 16 of 24 unverified, and the pilot's confirm rate (5 of 8) says they're worth verifying. Cost: about 65,000 tokens per verifier.
3. **Keep only what can't be regenerated** in a run's directory in Git: `report.md`, `findings.jsonl`, `unverified.jsonl`, `fixes.jsonl`, `gates.jsonl`, the summaries and this file. `requirements.jsonl`, `tests.jsonl` and `survivors.jsonl` (730 KB here) are regenerated in seconds, except survivors, which mutmut's own state in `mutants/` keeps.
4. **One driver** for a run's stages, so the operator's part is the go, the push and the merge: inventory, mutation, survey and verify, triage, fix, gate, report, with each stage's output checked before the next starts.
5. **Generic for Haflinger:** the paths (`src/enterich`, `docs/specs`), the requirement ID pattern and the forbidden paths go into a configuration file of the harness; the stages and schemas stay.
6. **The next run** of the tests lens: the 16 unverified findings, then the other specs and modules, verified without a cap.

## For ADR-008

The pilot kept to its Compliance: commits only on `auto/` branches, nothing pushed to `main`, no spec, ADR or dependency changed, a failing test before every change, every verdict from another agent, every record schema-checked. The gate's forbidden paths now include `pyproject.toml`, `uv.lock`, the tool-list snapshot, `harness/` and `.claude/`, written into the ADR. With decisions 1 and 2 taken, ADR-008 can be accepted.
