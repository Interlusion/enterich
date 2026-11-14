# Retrospective: the tests lens's third run, 2026-11-14

A small run of the tests lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)) on the two modules with the most survivors left, `enterich.app` and `enterich.erpnext`, after [the second run](../2026-11-12-tests-2/retrospective.md). Its purpose was to run the changed flow for real ([the guide](../../../docs/guides/improvement-pipeline.md)): a pattern and the test files in each verdict, the ratchet before its findings' fixes, branches planned by test file, each fix's outcome as a checked record, and a gate that pushes. Its decisions below are proposals until the operator takes them.

## Outcome

| Stage | Result |
| :- | :- |
| Inventory | 107 requirements, 206 DoD items, 692 tests |
| Mutation | 7,110 mutants: 6,593 killed, 515 survived, 2 timeouts; 273 survivors left to agents, 49 of them in `app` and 38 in `erpnext` |
| Survey | 2 agents, one per module: 5 findings from the 87 survivors |
| Verify | 5 verified: 4 confirmed, all as fixes, 1 refuted; every verdict named its pattern (or none) and its test files |
| Triage | 4 to fix; 1 ratchet, `limit-not-at-boundary`, from two findings in `erpnext` |
| Plan | 2 branches that share no test file: `auto/tests-integration-service` (2 fixes), `auto/tests-ratchet-limit-not-at-boundary` (the ratchet and its 2 findings) |
| Fix | 2 fixes committed and accepted by their review. The ratchet's test was committed and rejected by its review; its 2 findings were skipped |
| Outcomes | accepted 2, rejected 1, missing 2 |
| Gate | `auto/tests-integration-service` passed, the end-to-end tests included and none skipped. The ratchet's branch was refused: its commit belongs to a fix no review accepted |
| Pushed | `auto/tests-integration-service`, by `gate.py --push`, without a second run of the checks |

The two fixes: every rejection line is a warning whatever its cause, and the start draws no deprecation warning from the SDK (ADR-003). Neither names a requirement; both rest on the code's own contract.

## Cost

| Part | Agents | Subagent tokens | Time |
| :- | -: | -: | -: |
| Survey and verify | 7 | 758,000 | 10 min |
| Fix and review | 6 | 649,000 | 23 min |
| All | 13 | 1,407,000 | |

Per accepted fix: about 703,000 tokens, against 188,000 per merged test in the second run. Per 10 agents: 1.5 accepted fixes, against 3.1.

## What went wrong, and what changes

| Problem | Effect | Change |
| :- | :- | :- |
| The estimate before the run was 20 findings and 60 agents | The surveys made 5 findings of 87 survivors: the rest they judged noise, equivalent or part of one gap | Estimate from the last run's findings per survivor in the same modules, not from the count of survivors |
| The first ratchet was no class. Two neighbouring findings in one module shared `limit-not-at-boundary`; the threshold of two locations made a ratchet of them | Its agent wrote a test that names the two findings' places. The review rejected it: not generic over limits, the pattern still open in the same module (the 10 MiB response limit), repeating two tests | Not yet: a higher threshold, and patterns narrow enough for one test (decisions 1 and 2) |
| The ratchet's test read `vars(Erpnext)` to walk over the client's calls | Under mutmut the class also holds every mutant's copy of a method; the review reproduced `mutmut run` failing to collect its stats. Merged, it would have stopped the next run's mutation step, and the gate doesn't run mutmut | Not yet: the fix and ratchet prompts name the trap; a test that walks over a module's members takes them from a fixed list |
| Nothing plans a run again without a ratchet no review accepted | Its 2 findings are missing in `outcomes.json` and stay open | Not yet: `plan.py` leaves out a ratchet and a fix that have an outcome (decision 3) |
| The local `main` was two Dependabot merges behind `origin/main` | The fix branches were cut from `origin/main` and the gate run with `--base origin/main`; with its default the gate would have counted four commits as the branch's | Not yet: the gate's default base is `origin/main` after a fetch |
| The turn's token target counts output tokens | `+10m` was never near; the budget stop didn't run | The stop is still untested in a real run |
| A fix agent's worktree is about 150 MB with its environment, not 20 MB | Three worktrees held 445 MB until the cleanup | `cleanup.py --remove`; it ran here after the workflow, and can run during one |
| The session wrote `findings.jsonl` and `outcomes.jsonl` from the workflows' result files with a few lines of script each time | By hand, as before | Not yet: a script of the harness does it (decision 5) |

## What worked

- **The verdict's test files.** All three commits of the fix stage changed exactly the file their verdict named.
- **The plan.** Two branches with no file in common; no conflict was possible, and none had to be resolved.
- **The ratchet reviewed first.** Its rejection cost two agents. Nothing was built on it: its findings' agents never started.
- **The outcomes record and the gate's rule.** The gate refused the rejected commit's branch from `outcomes.json`, without running a check.
- **The push through the gate.** The branch that had passed was pushed at once by `--push`.
- **No test skipped.** The gate's tests ran with the end-to-end site and would have failed on a skip.
- **The cleanup.** The workflow's worktrees and branches were where and named as the script assumes.

## To look at

The verifier confirmed the rejection line's level as a gap. The second run had refuted the same finding as unspecified. The verifier knew, and argued from what was merged since: the levels of the other events are pinned now, and the operator's sample wanted two of those tests. Nothing in the pipeline remembers a refutation from one run to the next; a suppression would. Whether a verdict may overturn an earlier one is the operator's to say.

## Decisions proposed

The earlier retrospectives' decisions stand. In addition:

1. **A ratchet from three findings in at least two files**, not from two locations. Two neighbouring findings are closed by two tests.
2. **`limit-not-at-boundary` leaves the vocabulary**, or is split by the kind of limit. Limits live in different modules in different shapes; one test doesn't walk over them.
3. **`plan.py` plans only what has no outcome**, and no ratchet that has one, so planning a run again takes up what is missing.
4. **The tests lens rests on `app` and `erpnext`.** Two fixes for 1.4 million tokens, both without a requirement, is past the point of paying. What the other modules' 186 survivors would yield is open; the next lens says more about the code.
5. **A script writes the workflows' results to the run's records**, the first part of the driver.

## A second fix stage, the same day

Decisions 1, 2, 3 and 5 were built after the run: the higher threshold for a ratchet, `limit-not-at-boundary` out of the vocabulary, `plan.py` planning what a fix stage left, and `record.py` writing a workflow's result to the records. The run was then planned again. `plan.py` left out the two accepted fixes and the rejected ratchet and gave its two findings one branch, `auto/tests-unit-erpnext`. Both were fixed with a test each and accepted: a list lacking exactly three fields names all three and counts none (REQ-001-PRS-F018), and a refusal of 300 characters is kept whole while one of 301 is cut (REQ-001-PRS-F008). The gate passed the branch and pushed it.

| | Agents | Subagent tokens | Time |
| :- | -: | -: | -: |
| Second fix stage | 4 | 189,000 | 3 min |
| The run with it | 17 | 1,596,000 | |

The run ends with 4 fixes accepted, the ratchet rejected, and nothing missing: about 399,000 tokens per accepted fix. `workflows.jsonl` holds each workflow's agents and tokens. The rejected ratchet's commit stays on its local branch, unpushed. `groups.json` now holds the second plan; the first is in the commit before.

## For ADR-008

The run kept to its Compliance: commits only on `auto/` branches, nothing pushed but an `auto/` branch through the gate, no spec, ADR or dependency changed, a test before every change, every verdict and review from another agent, every record checked before a later stage read it. The run's records are committed on the pipeline's own branch, as in the runs before.
