# Retrospective: the tests lens's fourth run, 2026-11-14

A run of the tests lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)) on the nine tool modules, `enterich.tools` and those below it, which [the third run](../2026-11-14-tests/retrospective.md) left out. Its purpose was to see what the lens still yields on modules no survey had read since the second run, with the flow as changed after the third: a ratchet from three findings in two files, `plan.py` and `record.py`. Its decisions below are proposals until the operator takes them.

## Outcome

| Stage | Result |
| :- | :- |
| Inventory | 107 requirements, 206 DoD items, 692 tests |
| Mutation | As the third run, since nothing on `main` changed: 515 survived, 273 left to agents, 128 of them in the tool modules |
| Survey | 3 agents, 41 to 46 survivors each: 4 findings. The batch of five smaller modules gave none, though it held 17 survivors of the same class (below) |
| Verify | 4 verified: 3 confirmed, all as fixes, 1 refuted, since an end-to-end test kills its mutant |
| Triage | 3 to fix; no ratchet: two findings share `refusal-by-prefix`, below the threshold of three |
| Plan | 2 branches that share no test file |
| Fix | 3 fixes committed, all accepted by their review |
| Outcomes | accepted 3, nothing missing |
| Gate | Both branches passed, the end-to-end tests included and none skipped |
| Pushed | `auto/tests-integration-procure-to-pay-drafts` (1 fix), `auto/tests-integration-return-drafts` (2 fixes), by `gate.py --push` |

The three fixes are one kind of gap: the duplicate refusal and warning of a purchase invoice, a purchase return and a debit note's update were checked by their start and the other document's name, not by what they say matched (REQ-005-PRS-F006, REQ-005-PRS-F009, REQ-001-PRS-F005). None adds a test: each tightens existing tests to the whole text, as the sales side's tests already do.

## Cost

| Part | Agents | Subagent tokens | Time |
| :- | -: | -: | -: |
| Survey and verify | 7 | 424,000 | 2 min |
| Fix and review | 6 | 308,000 | 4 min |
| All | 13 | 732,000 | |

Per accepted fix: about 244,000 tokens, against 399,000 in the third run with its second fix stage and 188,000 in the second run. Per 10 agents: 2.3 accepted fixes, against 2.4 and 3.1. Per agent: about 56,000 tokens, against 94,000 and 58,000. The numbers are `workflows.jsonl`'s, which `record.py` wrote.

## What the run says about the third run's cost

The third run's agents cost about twice the second run's. This run had the same model and the same flow as the third and is back at the second run's cost per agent. So neither the model nor the changed flow explains the third run: its two modules do, `app` and `erpnext`, and the rejected ratchet.

## One survey batch read again by another model

Outside the run's records, two Sonnet agents got the survey prompt of the second and the third batch, without this run's answers.

| Batch | Survivors | This run's survey | Sonnet |
| :- | -: | -: | -: |
| 2: `procure_to_pay`, `returns` | 41 | 3 findings, all confirmed | 0 |
| 3: five smaller modules | 46 | 0 | 0 |

In the second batch, where there was something to find, the other model found none of it. The third batch's two zeros don't mean there was nothing to find: both surveys missed the same class there (below). One agent per batch is an indication, not a measurement. The two agents took 157,000 tokens, which the cost table above doesn't count.

## What went wrong, and what changes

| Problem | Effect | Change |
| :- | :- | :- |
| A survivor that an end-to-end test kills reached a survey again | A finding and a verifier to refute it; a second verdict had to set the end-to-end tests' half of a finding aside | Not yet: the second run's decision 2, end-to-end tests in the mutation step for the survivors of the others |
| The third finding has the pattern of the other two in a warning, and its verdict named none: `refusal-by-prefix` says "refusal" and "by its start" | Three findings of one class in two files counted as two; with the pattern named it would have been a ratchet | Not yet: the pattern's meaning is widened (decision 2) |
| The estimate before the run was 7 findings, 22 agents and 1.7 million tokens | 4 findings, 13 agents, 732,000 tokens | Estimate the tokens per agent from a run on like modules, not from the last run |
| The survey of the third batch missed 17 survivors of the class the second batch found: the payment entry's, the journal entry's and the sales invoice's duplicate refusal and warning, checked by their start and a name, and the default kind of `drafts.duplicate_warning` | The class stayed open in three modules the run had read | A generic test closes a class wherever it is; one was written after the run (below) |
| The session starts each script and workflow | By hand, as before; no record was written by hand | The driver, still open |

## What worked

- **`record.py`.** Both workflows' results went to the records by the script, with their agents and tokens.
- **The threshold.** Two findings sharing a pattern got two fixes and no ratchet.
- **The plan.** Three fixes on two branches by their test files; each commit changed only the file its verdict named.
- **The gate and the cleanup.** Both branches passed and were pushed without a second run of the checks; three worktrees and their branches were removed.

## Decisions proposed

The earlier retrospectives' decisions stand. In addition:

1. **The survey keeps the session's model.** A cheaper survey saves little and may miss what there is.
2. **`refusal-by-prefix` becomes "a refusal's or a warning's text is checked by a part of it, not by what it says"**, under a name that fits. This run's three findings would then have been one ratchet: a generic test over every create and update that can warn of a duplicate.
3. **The tests lens rests.** Four runs have read every module but `auth`, `config`, `shapes` and `log`, whose 57 survivors would give about two findings at this run's rate. The next lens says more about the code.

## Found after the run

In checking decision 2, the operator's question was whether one test can walk over the class. It can: every duplicate refusal and warning comes from `drafts.refuse_duplicates` and `drafts.duplicate_warning`, called in nine places across five modules. The run's survivors held the same mutants at the four places in `bank_and_cash`, `record_to_report` and `order_to_cash` that no finding named, and at the helper's default kind: 17 left to agents, none in a finding. A branch outside the pipeline, `test/duplicate-texts-whole`, tightens their tests to the whole text; each of the 17 mutants, applied by hand, fails them.

Decision 2 was taken: `refusal-by-prefix` is now `text-by-part`, "a refusal's or a warning's text is checked by a part of it, such as its start or a name it holds, not by what it says". This run's findings name the old pattern, so triage refuses them if they are sorted again. The finding weakens decision 1's ground, as both models' surveys missed the class in the third batch, and narrows decision 3: the class is closed before the lens rests. The operator took decisions 1 and 3 as well.

## For ADR-008

The run kept to its Compliance: commits only on `auto/` branches, nothing pushed but `auto/` branches through the gate, no spec, ADR or dependency changed, a test before every change, every verdict and review from another agent, every record checked before a later stage read it. The run's records are committed on the pipeline's own branch, as in the runs before.
