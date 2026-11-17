# Analysis 003: The improvement pipeline after three lenses

| Meta | Value |
| :- | :- |
| **Date** | 2026-11-17 |
| **Status** | Draft |
| **Author** | loxy (drafted with Claude) |
| **Audience** | The operator; whoever builds the method's skill for other repositories |
| **Purpose** | What three lenses and seven runs showed about the method, which parts hold across lenses, and what to prepare now for the parent and child skills |

## 1. Executive Summary

Seven runs of three lenses (tests four times, security twice, docs once) cost about 37M tokens, almost three quarters of it in one run, and confirmed 210 findings. What reached deployments: a token check that accepted a malformed client claim, a lock that kept parallel creates under the drafts limit, a guide that left ERPNext's own MCP endpoint open, and tool descriptions that misled the agent model. Every lens follows one shape: a script writes the run's universe from a vocabulary that a coverage check holds to the repository, one agent surveys each entry, another tries to refute each finding against a bar of evidence set per kind of finding, and the operator's suppressions and the gate do the rest. What changes between lenses is small and nameable: the vocabulary, the finding's kinds and fields, the evidence bar and the fix route. A lens's first run finds most of what it will find; its second finds mainly gaps in the nets the first added. Before the method moves to the skills repository, two steps make the split mechanical: one configuration file for Enterich's values in the harness, and one file for what the prompts say about Enterich (§4).

## 2. Context / Motivation

[Analysis 002](analysis-002-improvement-pipeline-after-two-runs.md) looked at the pipeline ([ADR-008](../arc42/adr/ADR-008-improvement-pipeline.md)) after two runs of its first lens and mapped its parts onto a parent skill and a child per repository (its §3.8). Since then the tests lens ran twice more, the security lens twice and the docs lens once, its deterministic part first ([`tests/repo/test_docs.py`](../../tests/repo/test_docs.py)). The operator asked what to write down now so that the skill, built later, is easier and better.

Scope: the seven runs' records and retrospectives in `harness/runs/`, the harness and the workflows on `main` after PR #87.

## 3. Findings

### 3.1 The seven runs

| Run | Lens | Agents | Tokens | Confirmed | Acted on | Tokens per confirmed |
| :- | :- | -: | -: | -: | :- | -: |
| 2026-11-12-tests | tests | 21 | 1.24M | 5 | 5 tests | 247k |
| 2026-11-12-tests-2 | tests | 472 | 27.30M | 157 | 150 tests, 1 code fix | 174k |
| 2026-11-14-tests | tests | 13 | 1.41M | 4 | 2 fixes | 352k |
| 2026-11-14-tests-2 | tests | 13 | 0.73M | 3 | 3 fixes | 244k |
| 2026-11-15-security | security | 60 | 3.67M | 18 | 10 fixes through the gate, 2 by hand | 204k |
| 2026-11-16-security | security | 27 | 1.43M | 12 | 2 by hand, 11 suppressed (one finding did both) | 119k |
| 2026-11-17-docs | docs | 19 | 1.49M | 11 | 11 by hand | 135k |

Tokens are subagent tokens from each run's `workflows.jsonl` and retrospective, fix stages included where a run had one. Precision as the operator judged it: a random sample of 12 merged tests, all wanted (`2026-11-12-tests-2/sample.jsonl`); the docs run's 11, all taken; the second security run's 11 suppressed findings were real but not worth a change, which the operator judged, not the verifiers. No lens has yet had a confirmed finding the operator called wrong.

What reached deployments: the token check accepting a non-string `azp` (tests lens); creates sent at once passing the drafts limit, and the configuration guide naming a setting Frappe ignores, which left its MCP endpoint open (first security run); the invoice creates' descriptions saying the posting date defaults to today, where a later update moves it (docs). Each lens found something its predecessors could not have.

### 3.2 One shape, five things that differ

Every lens runs the same stages. What a lens adds:

|  | Tests | Security | Docs |
| :- | :- | :- | :- |
| Vocabulary, held to the repository | The specs' requirements and DoD items; mutmut's survivors | `promises.jsonl`: one per scope line of `SECURITY.md` and rule of `AGENTS.md`, the policy's lines checked against it | `documents.jsonl`: every document in scope in exactly one record |
| Inventory | `inventory.py`, `mutation.py` | `surface.py`: tools, requests, log calls, settings | `documents.py` |
| Survey unit | A spec, a batch of modules | A promise | A record of documents |
| Kinds, and the bar to confirm | `dod-gap`, `mutant-gap`, `weak-test`: a test shown red | `breach`: reproduced; `unproven`: a test that would miss the change named | `drift`: both sides quoted, run where only running shows the code's |
| Fix route | The fix workflow and the gate | The fix workflow and the gate; by hand for a small run | By hand: the gate lets no document through |

Everything else is shared: a finding's key and its suppression, `record.py` with its secret scan, triage's report and classes (fix, proposal, drop), the plan by test file, the gate's rules, the budget's reserve, `--since` for a run after the first. The security and docs workflows are the same script but for their schemas and prompts: about 150 of their 200 lines each are identical (the cap, the batches, the merge by key, the budget check, the pipeline). The tests lens's workflow is older and differs more, with its sweep and its batches of modules.

So a lens is a small definition: a vocabulary with its coverage check, an inventory, a finding schema, a survey prompt, a verify prompt with its bar, and the rule for which side a fix goes to. The parent can hold the engine and the generic lenses; a child names its vocabularies and fills in the facts.

### 3.3 Where the yield is

- **A lens's first run finds most.** The tests lens went from 157 confirmed findings to 4 and 3; security from 18 to 12, of which 10 were gaps in nets the first run had added.
- **A second run finds its own nets.** Each fix to a check is new code the next run finds gaps in. The operator called further hardening over-engineering, and the rule is now written down: the pipeline's own checks are nets, their gaps are suppressed, and only what protects a deployment is fixed (`harness/README.md`, the security lens).
- **Deterministic checks first.** The docs lens's scripted part found nothing at once but made the agents' run cheaper and its findings sharper: no agent spent tokens on an input name or a default.
- **High precision, falling yield.** The verify stage confirms 62 to 100 % of what the surveys report, and the operator has rejected none of it. What falls is the number of findings worth a change, not their quality.

### 3.4 When a lens runs again

Each lens rests by its own rule (`harness/README.md`): the tests lens once survivors no longer pay; security while neither `src/` nor the configuration guide changes; docs while nothing a record reads changes. A run after the first takes `--since <commit>` and surveys only what changed.

`--since` sees files. An ERPNext upgrade changes behaviour that the specs, guides and tool descriptions rely on, and in the repository only a version pin changes, which no promise or record reads against. A full run of the security and docs lenses at a minor release, or after an ERPNext major version, catches what `--since` can't, at about 1.5M tokens a lens.

### 3.5 Fixing by hand

Of the last three runs' fixes, 15 were made by hand and 10 through the fix workflow. The fix workflow pays where there are many fixes in test files (150 in the second tests run); for a handful, or for documents the gate doesn't take, the session fixes them in less than a workflow costs (the first security run's fix stage: 25 agents, 1.3M tokens, 11 fixes). What the gate allows (tests, code, changelog) is a choice about what may change unattended, not a limit of the method: a child could allow guides.

### 3.6 Parent and child, refreshed

Analysis 002's §3.8 still holds; three lenses sharpen it.

| Part | Today | Parent or child |
| :- | :- | :- |
| The stages, the record schemas, keys, suppressions, classes, the budget's reserve | `harness/`, the workflows | Parent |
| The survey and verify engine: cap, batches, merge by key, budget check | Copied between `improve-security.js` and `improve-docs.js` | Parent, one engine |
| The lenses: kinds, evidence bars, survey and verify questions, fix route | The workflows' prompts and schemas, `triage.py`'s `LENSES` | Parent, as generic lenses |
| What the product is, its threat model, its contract | About 23 lines across the workflows' prompts naming Enterich, ERPNext, `src/enterich/` | Child: a short description the prompts take in |
| Vocabularies: promises, documents, patterns, suppressions | `harness/*.jsonl` | Child, as data |
| Paths and patterns: the requirement ID, the specs' glob, the code under mutation, the mutant prefix, the documents' scope, the policy file, the tool snapshot | About 15 constants in `inventory.py`, `triage.py`, `surface.py`, `documents.py`, `gate.py`, `pyproject.toml` | Child, in one configuration file |
| Checks, forbidden and allowed paths, commit format, branch prefix | `gate.py`'s `CHECKS`, `FORBIDDEN`, `ALLOWED`, `COMMIT` | Parent's minimum, child's additions |
| How the gate collects main's tests, installs the branch and reaches the end-to-end site | `gate.py`'s `COLLECT`, `uv sync --locked`, `E2E_ERPNEXT_URL` | Child: the checks hook, beside the tests' check whose results they are compared with |
| An inventory that reads the product's code | `surface.py` (the ERPNext client's calls, the log's events, the settings) | Child: one function per surface, the parent asks for the list |
| Trailers | Taken from the session as arguments | Session, never the method |

Two things a child needs that analysis 002 didn't name: the product description for the prompts, and inventory code that knows the product's structure. Both are small for Enterich and will differ entirely for Haflinger.

### 3.7 What no lens looks at

- **The contract's own soundness:** whether a spec is unambiguous and verifiable, whether two specs contradict each other (the docs run met one by chance, REQ-001 against REQ-006), whether an ADR's reasons still hold.
- **The fake against ERPNext** (analysis 002, §3.5): the integration tests run against `FakeErpnext`; where it differs from ERPNext, they pass and prove nothing.
- **Agent usability:** whether an agent model uses the tools as meant ([ITEM-009](../backlog/item-009-agent-eval-suite.md)).
- **The code itself:** the fourth lens of ADR-008, not built.

## 4. Recommendations

In this order:

1. **One configuration file for Enterich's values in the harness** (§3.6; analysis 002's recommendation 3): the paths, patterns, scope and the gate's lists, read by the scripts; the tests keep their place. The file becomes the child's hooks.
2. **One file for what the prompts say about Enterich:** the product, its contract, its threat model's pointers, read by the workflows as an argument, so the prompts name no product.
3. **A full run at a minor release or an ERPNext major version** for the security and docs lenses (§3.4); `--since` otherwise.
4. **Fake against ERPNext** as the next step of the pipeline, then a one-off review of the specs and ADRs by the specifying-requirements skill's gates rather than a lens (§3.7).
5. **The parent, when Haflinger adopts the method** (ADR-008's second trigger): start from the shared survey and verify engine of §3.2 and the generic lenses, and let the first child be Enterich's files from 1 and 2.

## 5. Open Questions

- Whether a child may let the fix stage change guides (§3.5), or documents stay by hand.
- How a lens's rest is measured across lenses: tokens per confirmed finding falls with every run, and what is worth a change falls faster. Analysis 002's §5 asked the same for one lens.
- Whether the tests lens's workflow should move onto the shared engine before the split, or stay as it is.
