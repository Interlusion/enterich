# Analysis 002: The improvement pipeline after two runs of the tests lens

| Meta | Value |
| :- | :- |
| **Date** | 2026-11-12 |
| **Status** | Draft |
| **Author** | loxy (drafted with Claude) |
| **Audience** | The operator deciding ADR-008; whoever builds the method's skill for other repositories |
| **Purpose** | What the pilot and the second run showed, what to change before the next run, and what of the pipeline is generic |

## 1. Executive Summary

Two runs of the tests lens merged 150 tests and found one code defect: a validly signed token with a non-string `azp` was accepted. Mutation survivors fell from 934 to 515 of 7,096 mutants, and those left for agents from 638 to 273. The method works: findings rest on schemas, a second agent's verdict, a red check and a gate, and no record or commit broke a rule of ADR-008. What doesn't work yet is scale. Seven of seventeen branches conflicted and nine commits repeated tests from other branches, because the fix stage grouped work by where findings came from instead of by the files a fix touches. And the pipeline fixed instances where it should have fixed classes: the ratchet stage, which turns a class of finding into a check, never ran. The tests lens is past its best yield, about 40 % of the second run's material is left, and its findings are now rarely code defects. The operator judged a random sample of 12 merged tests and would have wanted all 12. Next: the ratchet for the second run's classes, a planner that splits work by file, and then lenses that look at code and fakes rather than tests (§4). The method should end as a parent skill with a child per repository; the harness already separates most of what a child would fill in, and §3.8 maps the rest.

## 2. Context / Motivation

[ADR-008](../arc42/adr/ADR-008-improvement-pipeline.md) (Proposed) set up an improvement pipeline: deterministic stages and agents with fixed schemas, commits only on `auto/` branches, the operator merging. Its first lens, tests, ran twice on 2026-11-12:

- the pilot on REQ-001 and the modules `shapes` and `tools` ([retrospective](../../harness/runs/2026-11-12-tests/retrospective.md));
- the second run over every spec and every module, every finding verified, one branch per survey ([retrospective](../../harness/runs/2026-11-12-tests-2/retrospective.md)).

After the second run the operator asked four questions: how to plan changes with the fewest merge conflicts; whether the pipeline concentrates too much on tests and needs more focused workflows; whether mutation testing is the only valid approach; and what software factories look like. The operator also set the end state: a skill in another repository, a parent holding the method and a child per repository tailoring it, for Enterich and Haflinger alike.

Scope: the two runs' records in `harness/runs/`, the harness and workflows on `chore/improvement-pipeline` at the time of writing, and a mutation run on `main` after PR #68 (not committed; its counts are in §3.1). Published factory practice (§3.6) is from memory of the literature, not re-checked for this analysis.

## 3. Findings

### 3.1 What the two runs did

|  | Pilot | Second run |
| :- | -: | -: |
| Scope | REQ-001; `shapes`, `tools` | 7 specs; 16 modules in 10 batches |
| Findings / verified / confirmed | 24 / 8 / 5 | 172 / 172 / 157 |
| Fixes committed and accepted | 5 | 150 (4 found closed earlier on the branch, 3 rejected by review) |
| Merged | 5 tests (#47 to #51) | 145 tests (#52 to #68) |
| Code defects | 0 | 1 (fixed by hand, `fix/client-claim-not-a-string`) |
| Agents / subagent tokens | 21 / 1.2 M | 472 / 27.3 M |
| Tokens per merged test | ~250,000 | ~188,000 |
| Merged fixes per 10 agents | 2.4 | 3.1 |

Mutation survivors over `src/enterich/` (7,096 mutants; unit and integration tests):

|  | Survivors | Left for agents after the filter | Score |
| :- | -: | -: | -: |
| Before the pilot | 934 | 638 | 86.7 % |
| Before the second run | 924 | 628 | 86.9 % |
| After #68 | 515 | 273 | 92.6 % |

Of the 340 mutants the second run's fixes named, 334 are killed. The six left: two belong to the two rejected `auth` fixes, four to mutants the fix agents judged equivalent or left out. Most survivors left for agents: `app` 49, `erpnext` 38, `tools.bank_and_cash` and `tools.procure_to_pay` 25 each; `invoicing` fell from 51 to 7, `__main__` from 27 to 1.

The tests outside the end-to-end ones still run in about 20 s.

### 3.2 Merge conflicts are a planning problem

The fix stage gave each survey a branch. A spec's survey and the survey of the modules implementing it then add tests to the same test files: seven branches conflicted with the ten merged first, and nine commits on those seven branches repeated a test main had gained in the meantime, wholly or in part. Resolving the conflicts by a script (keeping both sides) broke four branches; the duplicate check by seven read-only agents found it.

Within a branch the order worked: four fix agents found their gap closed by an earlier fix on the same branch and committed nothing. The lesson is that work which touches the same files belongs in one sequence, and work which doesn't can run in parallel. Three ways to get there, cheapest first:

1. **Plan by files.** Before the fix stage, predict for each finding the test files it touches. The inventory already knows which test files cite which requirement and test which module, and a finding names its location. Group findings into sets with disjoint files; each set is a branch. Branches that share no file can't conflict.
2. **Waves.** Merge a wave before branching the next, so every branch starts from a fresh `main`. Seventeen long branches at once was the other extreme.
3. **A merge queue in the driver.** Before the gate, an agent rebases each branch onto the latest `main` and resolves conflicts with the tests run after each one; branches merge one after another.

The first removes most conflicts by construction; the third catches what the prediction misses.

### 3.3 Instances, not classes

Many of the 157 gaps are instances of a few classes:

- yes/no fields compared with `==`, where `0 == False` lets an unconverted field pass (REQ-001-PRS-F014): found in drafts, tax templates, parties, addresses, invoices;
- limits tested well past the boundary but never at it: 1 MiB bodies, 8 KiB tokens, 100 addresses, page limits, 64-character log fields;
- a flag, field list or argument dropped without a test noticing, wherever results are compared as whole dictionaries;
- refusal texts checked by a prefix, not by what they name.

Each instance got its own test. ADR-008's stage 6, the ratchet, says a confirmed class that a script can check becomes a CI check so the next run starts higher; it never ran. One generic test, for example a walk over every tool's result asserting that yes/no fields are `bool`, guards a class in every operation, including ones not yet written, and would have replaced several instance tests. It also serves the operator's goal of no useless tests: a class check can make instance tests redundant, and ADR-008's rule (remove a test only when the others kill every mutant it kills) can then prove it.

### 3.4 The tests lens is past its best yield

- **What it finds:** one code defect in 157 confirmed gaps. The others are correct behaviour without a test: regression protection, not bug finding.
- **What is left:** 273 survivors for agents, 43 % of the second run's 628, concentrated in `app` and `erpnext`.
- **Stopping:** the pilot proposed that a lens stops on a scope after two runs in a row with fewer than one merged fix per ten agents. The second run had 3.1; a third run over the same scope would be the first real test of the threshold.
- **Proposals:** none. Every finding could be closed within the current specs. That says the specs are complete enough for this lens; it says nothing about whether they are complete, which is the docs lens's question.

The tests lens did what ADR-008 put it first for: the safety net is much denser before lenses that change code begin.

### 3.5 Mutation testing among other approaches

Mutation testing answers one question well: would the tests notice a change of this code? It doesn't answer whether the code is right, and in the integration tests it measures against a fake ERPNext. Other approaches fit this code base:

| Approach | Finds | Fit |
| :- | :- | :- |
| Fake against real ERPNext | Integration tests that pass only because `tests/fakes/erpnext.py` differs from ERPNext | High. Nearly every integration test asserts against the fake. Running the same scenarios against the fake and the end-to-end site and comparing what each answers measures the largest risk none of the runs looked at. |
| Property-based tests (Hypothesis) | Defects in pure logic: paging, cutting texts, signs of tax rows, rounding | High for `shapes`, `tools.drafts`, `tools.invoicing.tax_summary` |
| Fuzzing tool inputs | Inputs that pass the input schemas and shouldn't | Medium to high; a security-lens tool |
| Static rules (semgrep, stricter types) | Whole classes, deterministically | The ratchet's natural targets (§3.3) |
| Mutation testing | Behaviour no test notices | Keep; rerun on changed code only, and let survivors of the unit and integration tests go through the end-to-end tests before an agent sees them (several were refuted for that alone) |

### 3.6 What software factories look like

Published setups that work share a shape. Meta's papers on improving unit tests with LLMs (TestGen-LLM, 2024) keep a generated test only if it builds, passes repeatedly and adds coverage; their later work guides generation by mutants, as the tests lens does. Google's reports on LLM-driven code migrations split work by code ownership, land it in many small changes and keep people reviewing. Common to them:

- a work queue fed by a planner, not one fan-out over everything;
- many small changes merged quickly, through a merge queue;
- deterministic filters as the guard, agents inside fixed limits;
- people merging, and the acceptance rate of what people review as the main measure;
- triggers on events (a change, a dependency, a new version), not only periodic sweeps.

The pipeline has the shape: deterministic stages, schemas, a second agent's verdict, a gate, the operator merging. It lacks the planner and merge queue (§3.2), the ratchet (§3.3), a measured acceptance rate (§3.7) and event triggers. The main production line of a factory, a feature from a spec through test and code, isn't part of ADR-008 at all; the lenses are its maintenance line.

### 3.7 The acceptance rate, measured on a sample

The verifiers confirmed 91 % in the second run, against 62 % in the pilot, where only each survey's top four were verified. The reviewers rejected 3 of 157. ADR-008's first reconsideration trigger is the operator rejecting more than one in five confirmed findings, but the operator merged 17 pull requests of 145 tests within a session. If that merge didn't judge each test, the rate rests on agents alone. A random sample of 10 to 15 merged tests, judged by the operator against "would I have wanted this test", measures it at little cost.

The operator judged such a sample after this analysis was written: 12 of the 145, drawn at random, all 12 wanted, none rejected (`harness/runs/2026-11-12-tests-2/sample.jsonl`). The first trigger doesn't fire. Twelve with no rejection bound the rejection rate at about 22 % with 95 % confidence, so the sample supports the verify stage as it is without proving the rate under one in five; the next lens's sample adds to it.

### 3.8 Generic method and repository parts

The end state is a parent skill holding the method, and a child per repository filling in named hooks (template method). The parent is the entry point, loads the repository's child, stops if there is none, and checks the child's method version. What the parent fixes, a child can't change; where a child leaves a hook empty, the parent uses a default or stops.

The harness and workflows today, sorted that way:

| Part | Today | Parent (final) or child (hook) |
| :- | :- | :- |
| Stages, their order, the record schemas, keys and suppressions | `harness/`, the workflows | Parent |
| Commits only on `auto/` branches, a failing test first, a verdict from another agent, schema checks, no merge | ADR-008 Compliance, `gate.py` | Parent |
| Specs, the requirement ID pattern, the Definition of Done format | `inventory.py`: `docs/specs/req-*.md`, `REQ-\d{3}-(?:URS\|PRS)-N?F\d{3}` | Hook `sources` |
| Code under mutation, mutant ID prefix | `pyproject.toml` (`[tool.mutmut]`), `triage.py` (`^enterich\.`) | Hook `sources` |
| Paths the pipeline may not change | `gate.py` `FORBIDDEN` | Parent's minimum (specs, ADRs, agent rules, CI, its own harness) plus hook `scope` |
| Checks and what counts as green, the end-to-end site | `gate.py` `CHECKS`, `E2E_ERPNEXT_URL`; the fix workflow's `CHECKS` | Hook `verify` |
| Commit format, branch prefix, trailers | `gate.py` `COMMIT`; the fix workflow's `TRAILERS`, which hard-codes one session's URL | Hook `conventions`; the trailers come from the session, never from the method |
| Test helpers the agents may break to show red (`tests/fakes/`) | Workflow prompts | Hook `scope` |
| Areas for the planner (§3.2): which specs, modules and test files belong together | Not yet | Hook `areas` |
| Lens order, budget, stopping threshold | ADR-008, run arguments | Parent default, hook `priorities` and `stop_when` |

About a dozen repository-specific values sit in the harness and workflows today, each in a constant or a prompt line. Gathering them into one configuration file (the pilot's decision 5) is the step that makes the later split mechanical: that file becomes the child's hooks, the rest becomes the parent.

Two constraints from the skill format and the engine:

- **Delivery.** The engine is Workflow scripts run from Claude Code; a headless run (cron, CI) has no personal-scope skills. The parent ships as a plugin or vendored copy; the child lives in the repository, versioned with its code.
- **Engine version.** The second run's survey ran a stale copy of its script because it was called by name. A parent that loads workflows must pin them by path or version, the same way it checks the child's method version.

ADR-008's second reconsideration trigger already says the method moves to the skills repository when a second repository adopts it. Until then, building the parent inside Enterich would guess at which parts generalise.

## 4. Recommendations

In this order:

1. **Ratchet the second run's classes** (§3.3): generic tests for yes/no fields, limits at the boundary, and refusal texts, where a class has an instance in more than one operation. Then check with mutation testing which instance tests became redundant.
2. **Measure the acceptance rate** (§3.7): done, 12 of 12 wanted; the verify stage stays as it is. Repeat the sample after each lens's run.
3. **Gather the repository-specific values into one configuration file** (§3.8), the trailers first, since they name a session. This is the pilot's decision 5 and prepares the parent and child split.
4. **Planner, waves and driver** (§3.2), before the next large run: findings grouped by the files they touch, a wave merged before the next starts, a rebase by an agent before the gate, worktrees cleaned and branches pushed through `gate.py --push`.
5. **The next lenses:** first the comparison of the fake with the end-to-end site (§3.5), then docs (largely deterministic, much of it a CI check at once), then security against [analysis 001](analysis-001-excessive-agency-review.md). A third tests run waits until the next lenses have changed code.
6. **ADR-008:** take the decisions from 1 to 5 and both retrospectives into it while it is still Proposed, then accept it. Among them: the ratchet as a required stage of every run, planning by files, the stopping measure, verifying without a cap, and the lens order.

Each of 1, 3, 4 and 5 is a backlog item of its own.

## 5. Open Questions

- Does the stopping measure (merged fixes per ten agents) need the operator's acceptance rate in it, so a lens whose fixes people would reject doesn't look productive?
- Should the feature line (spec to test to code) become part of the method, or stay the development guide's steps that people and agents follow by hand?
- Where does the planner get "the files a fix touches" for a lens other than tests, when a finding is in code, not in a test file?
- Which hooks does Haflinger need that Enterich doesn't? Answerable only by writing its child; until then the hook list in §3.8 is Enterich's.
