# Analysis 004: The improvement pipeline before its move

| Meta | Value |
| :- | :- |
| **Date** | 2026-11-21 |
| **Status** | Draft |
| **Author** | loxy (drafted with Claude) |
| **Audience** | The operator; whoever builds the method's skill for other repositories |
| **Purpose** | Whether the planned path to the parent skill is the best one, which other methods there are, and what the pipeline catches that a review of each change doesn't |

## 1. Executive Summary

Before the pipeline ([ADR-008](../arc42/adr/ADR-008-improvement-pipeline.md)) moves to the skills repository, two steps were planned here: one survey and verify engine for the security, docs and code lenses, and scripts that take the repository as an argument. Weighed against other ways to get there, the goal holds, but the engine is better generated than interpreted: a Python step writes each lens's workflow from one template and the lens definitions, so each lens keeps its own workflow, the session passes what it passes today, and the proof that the prompts are unchanged is a text diff in Python (§3.2). A different method, reviewing each change against the contract instead of sweeping, was weighed too, and the records were replayed against the review the operator does today, a code review of every change: of the 237 findings the pipeline confirmed in twelve runs, 219 are of kinds that review doesn't look for (gaps in the tests, a rule written twice, a document the code no longer does), and of the other 18 only 10 were visible in the diff that introduced them, half of those in diffs of 700 lines or more (§3.4). Without the tests lens's adoption run, which cleared a backlog, 80 findings remain and 10 of them were visible in their diff. The sweep is the main net and the review of each change the first filter; both stay. A lens that reviews each pull request against the contract was not tested and may take over part of the sweep's work; what needs the whole code or running stays the sweep's. What to add: mutation testing in CI on the changed lines, which would move the largest class (117 findings) from agents to a check, and a review of fixes as deep as a feature's, since two of the 18 came from fixes, one of them the fix stage's.

## 2. Context / Motivation

[Analysis 003](analysis-003-improvement-pipeline-after-three-lenses.md) mapped the pipeline onto a parent skill and a child per repository (its §3.6) and named one engine for the lenses as a parent part. A handover then planned two steps in Enterich before anything moves:

1. **One engine for survey and verify:** `improve-security.js`, `improve-docs.js` and `improve-code.js` each carry a copy of the same engine; one Workflow script would take a lens's definition (its survey units, kinds, survey and verify questions, bar) as an argument, since a Workflow script reads no file. Proof without a run: for each lens the prompts rendered equal today's, word for word. The tests lens, older and of another shape, stays on its own workflow.
2. **The scripts take the repository as an argument:** every script under `harness/` finds the repository from its own path, so it works only from inside it. Proof: the harness's tests run the scripts from a copy outside the repository.

A third change was to follow on its own: the code lens's worth question (who acts wrongly today, what the change would add) asked by every lens, which changes the security and docs prompts.

The operator asked whether this is the best path, then whether a wholly different method would be better. They review every change with Claude Code's code-review, and things still slip through, because some need the whole picture. This analysis records the answers and the replay that tested them.

Scope: the workflows and the harness on `main` at v0.7.0, the twelve runs' records in `harness/runs/` (2026-11-12 to 2026-11-20), and the commits that introduced the findings replayed.

## 3. Findings

### 3.1 The planned steps against the code

**The lenses differ in prose, not in parameters.** The engine the three workflows share is the mechanics: the cap per survey, the batches, the merge by key, the budget's reserve, the handling of a finding no verifier answered. What differs is text, and more of it than units, kinds and a bar:

- The verify procedure: security confirms a breach only as reproduced and refutes it as a breach where only a missing test shows, with "unproven" as a second kind; code confirms with both sides quoted and asks the worth question before the class.
- What each class means is written per lens.
- The run's files: `promises.jsonl` and `surface.json` for security, `modules.jsonl` and `since.json` for code; the paragraph for a run since a commit differs per lens.
- Only the code lens filters a survey's findings by the concerns its record names (`RECORDS_CONCERNS`).
- The schemas' field descriptions differ (`kind`, `location`, `evidence`, `test_files`, `reproduction`). The agent reads them as it reads the prompt, so a proof of unchanged prompts has to cover them.

A definition as data is therefore mostly template text that refers to the brief, the finding, the run directory and the commit since which a run looks. The rule for that template (named placeholders, the since paragraph as a field of its own, a fixed set of blocks the engine computes: the kinds with their bars, the patterns, the read-only paragraph) is a decision step 1 needs before it starts. A richer template language would move the code into the data.

**The kinds are written twice already.** A comment in `improve-code.js` says the concerns are known to `harness/modules.py` and `harness/triage.py` too. A definition both the workflows and the Python read gives them one source.

**One runtime engine collapses three workflows into one.** A Workflow script imports nothing and its `meta` is a literal, so one engine is one workflow with the lens as an argument. The three skills the session offers today become one, and the guide (`docs/guides/improvement-pipeline.md`), `harness/README.md` and ADR-008 change with it.

**The prompts name the harness's paths** (for example that `harness/record.py` refuses a result holding a secret). After the move those scripts live in the parent; a prompt that names them by path changes at the move, unless the path comes from the arguments before it.

**A proof by rendering needs a JavaScript runtime.** The harness's tests read the workflows as text from Python. Rendering a prompt means running the script with stubs of the runner's globals (`args`, `agent`, `parallel`, `pipeline`, `log`, `phase`, the budget), and a stub `agent` that answers a survey with a finding, or no verify prompt is ever rendered. Node is on the operator's machine; CI's test jobs set up only `uv`, and the `ubuntu-24.04` runners carry Node without any job asking for it. A test that skips where Node is missing would be a check that passes while reading nothing, the failure `harness/project.py` already guards against. After the change a stored copy of the prompts tests only itself; the lasting test is that each lens renders, no placeholder is left, and the kinds equal what triage reads. The proof of equality is a one-off, given in the commit, as when the brief moved into `harness/project.toml` (`ba02bc5`), which kept one difference and named it.

**Step 2 is mechanical.** Beside the ten `ROOT = Path(__file__)…` lines, `harness/project.py` names `harness/project.toml` from the repository's root, the tests reach the repository through `gate.ROOT`, and the git commands of `gate.py` and `modules.py` run where the scripts are.

**The two settled proposals hold.** The tests lens stays on its own workflow and moves as it is, its fix stage (`improve-tests-fix.js`) with it. The worth question for every lens is its own change after step 1; it changes what the security and docs verifiers confirm, which only a run can show better, so it will be the first change of the series that needs one.

### 3.2 Other ways to the same goal

The goal: the method is reused across repositories, each child holds only what is its own, and the move doesn't change what the agents are asked.

| Approach | What it gives | What it costs |
| :- | :- | :- |
| One engine at runtime, definitions as arguments (the plan) | One script | The template rule; one workflow for three; a JavaScript runtime for the proof; the session assembles a larger argument |
| The workflows generated from one template and the definitions | One source; three workflows and skills as today; the session passes the brief as today; the proof is a diff of the generated files against today's, in Python, strongest where the first generation is byte for byte today's file | Generated code in the repository, held by a test that what is committed is what the step writes; a template that renames today's variables leaves a diff to be read line by line |
| The agents driven from Python (Claude Agent SDK or `claude -p`), no Workflow scripts | Every prompt rendered and tested in pytest; no dependency on a young Claude Code feature | The session's orchestration, the `/workflows` view, probably the billing; a larger change than this needs |
| The parent as a versioned package, the skill a thin layer over it | A child pins the parent's version, so a parent's prompt change reaches it when it chooses | A release process for the parent; the skills repository holds only the instructions |

Generation fits the operator's preference for derived copies from one source, and avoids every cost the runtime engine brings. Driving from Python is the path to keep in mind if the Workflow feature becomes a constraint again. Versioning is a question the move has to answer whichever way the engine is built: with two children, does a parent's prompt change alter the next run of both?

No tool known when this was written does this method: generic AI reviewers and security scanners don't survey against a spec contract, verify adversarially with suppressions, and gate fixes on branches. Mutation testing is the one part already taken from outside.

**Timing.** Analysis 003 names Haflinger as the second child. The engine is justified now: three copies within Enterich are three instances. Step 2 and the move are justified by reuse alone, and a parent's boundary drawn from one product may be drawn in the wrong place (whether `surface.py` is the only product-specific code, whether the brief misses fields). The second child is the better proof for step 2 than a copy of Enterich outside the repository.

### 3.3 A different method: review at the time of change

Weighed from scratch, the pipeline sweeps in batches: it surveys everything, or everything since a commit, then verifies, fixes on branches and gates. That is right for adopting an existing codebase, and the records suggest adoption is ending: the code lens's fifth run found 3 findings and dropped all, lenses rest until the code or a guide changes, later runs are runs since a commit. Several open problems come from the batches more than from the task: the CHANGELOG serialising a run's branches and dropped findings to be checked again (both in analysis 003's §3.6), and a suppression that misses a finding whose location moved.

The alternative weighed:

1. **Each lens reviews a pull request's diff** against the contract, with the same adversarial verify, and its findings land in the pull request that caused them. No branches to put in a row, no suppressions to drift (a dismissal is a review decision with its reason), and a cost that grows with the change. A full sweep stays for a repository's adoption and for a change of the specs or a guide that moves the bar.
2. **Every confirmed finding ends as a deterministic check, or it is a drop:** a test, a lint or architecture rule, a generated document that can't drift, a schema snapshot. The ratchets already do this for some classes; as the rule, the agents meet only what is new.
3. **The parent becomes thin:** a review per lens, the verify bar and the worth question, the rule above, a sweep for adoption.

Its cost: tokens on every change, and the loss of the whole view a sweep has. A rule written twice in two old modules is in no single diff. The replay in §3.4 tested part of that: what gets past the review the operator does today. It did not test a lens that reviews each pull request against the contract.

### 3.4 Replay: what got past the review of each change

The operator reviews every change with Claude Code's code-review, an agent that looks for correctness bugs in a change and can read the repository around it. Every finding the pipeline confirmed therefore got past such a review of the change that brought it, so the question is not whether the review would have caught them but why it didn't.

**Method.** Every finding of the twelve runs whose verdict is confirmed and whose class is fix or proposal (215 fixes, 22 proposals; the two confirmed drops left out), sorted by kind. For the kinds that could lie within one change, each finding was traced with `git log -L` on its function and `git log -S`/`-G` on its code to the commit that introduced it, and judged by what catching it needed. Assumptions and limits:

- Every introducing commit is taken as reviewed; that was the operator's practice, but it was not checked commit by commit (§5).
- "Introduced by" is the first commit that touched the function, unless the code it names came later. A heuristic: one later fix that changed the same handler (`dd2ce72`, before finding 17) was checked and had not introduced it.
- Two judgements of "visible in the diff" were checked by reading the diff (findings 1 and 10 below); the others rest on the finding's claim and evidence and the diff's size.
- The sorting by kind is a judgement of what a review of a change looks for; those 219 findings were not traced to their commits.

**By kind:**

| Kind | Lens | Confirmed | Does a review of the change see it |
| :- | :- | -: | :- |
| `mutant-gap`, `dod-gap`, `weak-test` | tests | 169 | No: a review judges the code, not whether a test would notice it change |
| `unproven` | security | 22 | No, for the same reason |
| `rule-twice`, `missed-pattern` | code | 17 | Rarely: the other copy, or the helper, is in code beyond the change, which a review rarely follows |
| `drift` | docs | 11 | Rarely: the sentence a change makes false is in a file the change doesn't touch |
| `breach` | security | 8 | Possibly |
| `lost-on-the-way`, `wrong-outcome` | code | 10 | Possibly |

219 of 237 are of kinds the review doesn't look for. 157 of the 169 tests findings came from one run, the tests lens's first full one on a codebase that had grown without it (`2026-11-12-tests-2`): a backlog cleared at adoption more than slips of single changes. Without that run, 80 findings remain, 18 of them of a kind that could lie within one change.

**The 18 that could lie within one diff:**

| # | Run | Finding | Introduced by | What catching it needed |
| -: | :- | :- | :- | :- |
| 1 | 2026-11-15-security | Creates sent at once all pass the drafts-per-hour count before any inserts (`tools/drafts.py:insert`) | `a681bdb`, 73 lines | Visible: a count, then an awaited insert |
| 2 | 2026-11-15-security | The configuration guide names a setting the pinned ERPNext image ignores, leaving its MCP endpoint open | `8cbcf10` (docs) | Knowledge of ERPNext, confirmed by a script run in the pinned image |
| 3 | 2026-11-15-security | `auto/` branches pushed with no secret scan: the gate runs none, CI's scan doesn't run on a push without a pull request | `522e744` | Code outside the diff: the gate and CI's triggers together |
| 4 | 2026-11-16-security | An insert Enterich gives up on but ERPNext commits is counted by nothing while its lock is released | `765fe9c`, the fix stage's fix of finding 1, 19 lines | Code outside the diff: the operation's deadline and the call timeout |
| 5 | 2026-11-16-security | The deployment-neutral test's host check misses a host followed by most characters | `5755dec`, 141 lines | Visible |
| 6 | 2026-11-16-security | The same test misses escaped and percent-encoded URLs and hosts without a scheme | `5755dec` | Visible |
| 7 | 2026-11-16-security | The same test skips a file that isn't valid UTF-8 | `5755dec` | Visible |
| 8 | 2026-11-16-security | The gate's secret scan reads `git log -p` without `--text`, so a secret in a file git treats as binary is never scanned | `522e744`, 2,479 lines | Knowledge of git |
| 9 | 2026-11-19-code | A failed JWKS fetch logs only the exception's class name (`auth.py:JwksCache._refresh`) | `8edd1d2`, 3,259 lines | Visible, in a large diff |
| 10 | 2026-11-19-code | A draft's fallback result starts a new warnings list and loses the duplicate warning (`tools/__init__.py:_written`) | `de2cb95`, a fix by hand, 51 lines | Visible |
| 11 | 2026-11-19-code | The journal duplicate check reads 1,000 rows and says nothing at the cap | `b8f0a5d`, 809 lines | Visible, in a large diff |
| 12 | 2026-11-19-code | A payment's references in another letter case are refused with a false cause | `a325c66`, 701 lines | Knowledge of ERPNext: it compares names regardless of case |
| 13 | 2026-11-20-code-2 | A token naming a key of another type than its `alg` ends as a 500, not a refusal | `8edd1d2` | Knowledge of PyJWT's exceptions |
| 14 | 2026-11-20-code-2 | A rejected `ENTERICH_ISSUER` is reported as `ENTERICH_RESOURCE_URL` | `8edd1d2` (origin less certain) | Visible, in a large diff |
| 15 | 2026-11-20-code-2 | A comment ERPNext answers too late is reported two ways, depending on which timeout fires | `2d58c74`, 107 lines | Code outside the diff: the operation's deadline |
| 16 | 2026-11-20-code-3 | When Enterich refuses to start, the unknown-variable warnings are never worked out | `8edd1d2` | Visible, in a large diff |
| 17 | 2026-11-20-code | A JWKS entry that makes PyJWK raise outside its own error type gets past both handlers | `8edd1d2` | Knowledge of PyJWT's exceptions |
| 18 | 2026-11-20-code | A purchase return matching two duplicate checks is refused naming only the first | `c93606f`, 1,017 lines | Visible, in a large diff |

Commit hashes are abbreviated; every finding's full record is in its run's `findings.jsonl`.

| What catching it needed | Findings |
| :- | -: |
| Visible in a diff under 150 lines | 5 (1, 5–7, 10) |
| Visible, in a diff of 700 lines or more | 5 (9, 11, 14, 16, 18) |
| Knowledge of ERPNext, a library or git, confirmed by running | 5 (2, 8, 12, 13, 17) |
| Code beyond the change | 3 (3, 4, 15) |

Of the five that needed outside knowledge, one was confirmed in the pinned ERPNext image (2); the other four by throwaway tests against the tests' fakes, which hold the code's behaviour but not ERPNext's or the library's: what ERPNext or PyJWT does came from the verifier's reading.

### 3.5 What the replay shows

- **The sweep is the main net.** 10 of 237 confirmed findings were visible in the diff that brought them, 10 of 80 without the adoption run; the rest needed the whole test suite, the whole code, the documents read against the code, or running. The operator's observation holds: the review of each change done today can't replace the sweeps. Both stay, the review as the first filter.
- **A lens per pull request is untested, not ruled out.** One that reads the specs and the tests as the sweeps do could find gaps in the tests (`dod-gap`, `weak-test`) and drifts of documents for the requirements a change touches. What it can't replace: the findings that need the whole code (the 17 rules written twice or patterns missed, and 3 of the 18), those that need running (5 of the 18), and a backlog at adoption.
- **Large diffs weaken the review.** Half the visible ones sat in feature commits of 700 to 3,259 lines.
- **Fixes introduce findings too.** Finding 4 came from the fix stage's fix of finding 1 (`765fe9c`, via an `auto/` branch), finding 10 from a fix by hand (`de2cb95`); both small diffs that their review passed.
- **Running is its own ingredient.** The five that needed knowledge of ERPNext, a library or git were confirmed by running, in the pinned image or against the tests' fakes. Neither kind of review reads its way to them.
- **The largest class can move to CI.** The 117 mutation gaps are found by a tool; run on a pull request's changed lines, it would show them before a sweep, without agents. This is §3.3's second rule, which holds for the batch pipeline as well.

## 4. Recommendations

1. **Keep the batch pipeline, and the review of each change beside it.** Don't replace the sweeps with the review of each change done today. A lens per pull request against the contract is a separate question, open until tried (§5).
2. **Build step 1 as generation:** one template and three lens definitions, a Python step that writes the three workflows, a test that what is committed is what the step writes. The proof is the diff of the generated workflows against today's, schemas included, with every difference named. Settle the template rule first (§3.1). The harness's paths in the prompts come from the arguments in the same step. Done after this analysis: `harness/engine.py` writes the three workflows from `harness/lenses/engine.js.tmpl` and a definition per lens, its first writing byte for byte the workflows before it. A definition keeps the prompts' `${...}` as they were; the script fills them when it runs, as before. The paths came with step 2: the prompts name the child's files through the brief's `child`, and the method's scripts by their names alone.
3. **Read the kinds from the definitions in `modules.py` and `triage.py` too,** so the kinds have one source. Done with step 1: each definition's `[kinds]`.
4. **Take step 2 with the second child,** or make the second child its proof. Taken before it: the scripts take the repository from the working directory and the child from `harness/` there, and a copy of them outside the repository does what they do inside it (`tests/repo/test_harness_repository.py`). What that copy can't show is whether the child's boundary is drawn in the right place; the second child stays its proof.
5. **The worth question for every lens stays a change of its own after step 1,** and is the first that needs a run to be trusted.
6. **Try mutation testing on a pull request's changed lines** in CI, as a check the operator weighs by its run time.
7. **Review fixes, the fix stage's and those by hand, as deeply as a feature,** and keep feature pull requests small enough to review, or review a large one in parts.
8. **Decide how a child pins the parent's version** before the second child runs.

## 5. Open Questions

- Did code-review run on every introducing commit, `8edd1d2` (2026-10-27, 3,259 lines) above all? If not there, three of the five findings visible in a large diff were never in front of a review, and the count of visible ones a review missed falls to seven.
- Would a lens that reviews each pull request against the specs and the tests catch the gaps in the tests and the drifts of documents a change brings, and at what cost per change? Trying it on the next few pull requests beside the sweeps would show it.
- When does Haflinger become the second child, and does it decide where step 2 happens?
- How long would mutation testing on changed lines take in CI, and which tool runs it on a diff?
- Does every confirmed finding end as a check, or only some classes, and who decides for a proposal?
