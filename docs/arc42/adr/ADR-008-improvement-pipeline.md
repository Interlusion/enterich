# ADR-008: An improvement pipeline of agents between deterministic stages, committing only on `auto/` branches

| Meta | Value |
| :- | :- |
| **Status** | Proposed |
| **Date** | 2026-11-11 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich's quality rests on its contract (the specs with their IDs and Definitions of Done, the ADRs, `AGENTS.md`) and on its gates (ruff, basedpyright, the unit and integration tests, the end-to-end tests against ERPNext, mdformat and the link check). Each change so far was proposed, reviewed and committed with the operator in the loop. Reviews found real defects, but each one took the operator's time, and nothing looked at the code base as a whole on a schedule: which tests prove nothing, which Definition of Done items have no test, where docs and code drifted.

The operator wants that improvement to run with as little human interaction as possible, in a way that can later serve other repositories of the same shape (Haflinger), while the specs and ADRs stay the contract.

A text loop of this kind ran on another project's tests (a per-turn procedure, a fixed rubric, an append-only ledger). Its retrospective found: state in committed files made it resumable and free of double counting; a single rater drifted, with nothing to notice it; a tag that meant "delete this test" couldn't be checked by the procedure; sampling and records weren't reproducible; there was no schema gate on records. It concluded that one agent per item in an isolated context, with schema-checked output and a deep verification before anything is acted on, would be the better engine.

A trial on `shapes.py` showed mutation testing works here: mutmut 3 made 257 mutants, the unit and integration tests killed 214 of them in about a minute on 8 cores, and the whole package has about 7,100. The survivors mix noise (an error message's first letter in lower case) with real gaps (no test notices `ensure_ascii` dropped, which changes how long a result with non-ASCII text counts).

`AGENTS.md` allows a commit or push only when the operator asks, which rules out unattended work.

## Decision

### Stages

A run takes one **lens** (a kind of finding) through fixed stages. Deterministic stages are scripts; judgement stages are agents, each with one item in its own context and a fixed output schema.

1. **Inventory** (script): the run's universe, written to the run's directory. For the tests lens: the requirement IDs and Definition of Done items of `docs/specs/`, the tests with the requirement IDs they cite, and mutation testing's survivors.
2. **Survey** (agents, read-only): candidates from the inventory, each a finding with location, claim, evidence and a tag from the lens's fixed vocabulary.
3. **Verify** (agents, read-only): one agent per finding tries to refute it against the code, the specs and, where the finding is about ERPNext, its source or the end-to-end site. Only confirmed findings go on; the rest are counted.
4. **Triage** (script): confirmed findings are matched against the backlog and the operator's suppressions, then sorted into **fix** (within the specs and ADRs), **proposal** (needs a spec, ADR or `AGENTS.md` change, or a new dependency) and **dropped**.
5. **Fix** (agents, one per finding, each in its own worktree): the development guide's steps, a failing `test:` commit, then the `fix:`, `feat:` or `refactor:`, with all gates green, end-to-end tests included, on a branch of its own.
6. **Ratchet**: where a confirmed class of finding can be checked by a script, the run proposes that check for CI, so the next run starts higher.
7. **Report**: the run's counts, its fix branches, its proposals; the operator merges, decides proposals and curates suppressions.

### Files

- `harness/`: the scripts, schemas, rubrics and tag vocabularies, and the operator's `suppressions.jsonl`. The image takes neither `harness/` nor its tools (the Dockerfile copies `src` and `tests`).
- `harness/runs/<date>-<lens>/`: a run's inventory, findings, verdicts and report, as JSON Lines and Markdown, committed on the run's branch, so a run can resume after an interruption and runs can be compared.
- `.claude/workflows/`: the engine, one Workflow script per lens. The stages and files are the method; the engine may change without them.
- Tools only the pipeline needs, mutmut first, go into a dependency group of their own (`harness`), outside the `test` group the image's `test` stage installs and the `dev` group CI installs.

### Lenses, in this order

1. **Tests:** Definition of Done items without a test and tests without a requirement, both ways; mutation survivors judged as noise, equivalent or a gap; tests scored against a fixed rubric. A test is a candidate for removal only when it kills no mutant another test doesn't.
2. **Security:** against [analysis 001](../../analysis/analysis-001-excessive-agency-review.md)'s threat model and `AGENTS.md`'s rules.
3. **Docs:** specs, ADRs and guides against the code, such as a catalogue table against the published tool schemas.
4. **Code:** quality within the ADRs' choices.

A lens is added after the previous one has run once and its retrospective is written.

### Stopping

- **A run** stops at the first of: its universe done, its budget of agents spent, or saturation, when further survey batches bring no new confirmed class of finding.
- **A lens** rests when its runs stop paying: a measure of confidence per lens, from its runs' confirmed findings, their precision as the operator judges them, and what the deterministic checks still find, says when another run isn't worth its cost. The measure and its threshold are open; the first lens's retrospective proposes them.

## Alternatives Considered

### Alternative 1: A text loop (`/loop`, `/goal`) as on the other project

One procedure per turn, the agent rating and recording items itself.

**Rejected because**: its retrospective found a drifting single rater and no gate on records; it stays fit for the tail of one-at-a-time steps, such as fixing confirmed findings in turn.

### Alternative 2: Coverage as the measure of tests

**Rejected because**: coverage shows what ran, not what a test would notice; mutation testing shows that. Branch coverage stays reported in CI.

### Alternative 3: Agents that also merge

**Rejected because**: the specs are the contract only while a person decides what changes them and what reaches `main`.

### Alternative 4: The pipeline in the skills repository from the start

**Rejected because**: generalising before one run guesses at the wrong parts; extracted after the first runs (Reconsideration Triggers).

### Alternative 5: Scheduled runs in the cloud

**Rejected for now**: a run's cost and its findings' precision are unknown until runs have been made here.

## Consequences

### Positive

- Findings rest on counts and verified evidence, not on one agent's impression.
- The operator's time goes into merging, proposals and suppressions, not into each step.
- Every confirmed class of finding that becomes a CI check stays fixed.
- The same stages fit any repository with specs, ADRs and gates of this shape.

### Negative

- Runs spend tokens, the verify stage most; a run's cost is known only after it.
- `harness/` is code of its own to maintain, with its own dependency group.
- Fix branches pile up if the operator doesn't merge or reject them.
- A wrong verification can still let a bad fix through; the gates and the operator's merge are what remain.

## Reconsideration Triggers

Revisit this decision when:

1. A lens's retrospective finds the verify stage confirming findings the operator rejects, more than one in five.
2. A second repository adopts the pipeline: move the method to the skills repository, with a per-repository configuration.
3. Runs have been made often enough to know their cost and value: then consider scheduled runs.

## Compliance

- The pipeline SHALL commit and push only on branches whose names start with `auto/`; it SHALL NOT push to `main`, create or push a tag, start a release, or merge.
- The pipeline SHALL NOT change `docs/specs/`, `docs/arc42/adr/`, `AGENTS.md`, `CLAUDE.md`, `.github/`, the `Dockerfile`, `server.json`, `pyproject.toml` and `uv.lock`, the tool-list snapshot (which changes only with its spec), or its own `harness/` and `.claude/`; a finding that needs such a change SHALL be a proposal in the report. The fix stage's gate (`harness/gate.py`) refuses a branch that does, and pushes only a branch that passed.
- Every fix SHALL follow the development guide: a failing test committed before the change, and every gate green, the end-to-end tests included.
- No finding SHALL reach triage without a verdict from an agent other than the one that made it.
- Every record SHALL pass its schema check before a later stage reads it.
- A test SHALL be removed only when mutation testing shows that the tests left kill every mutant it kills.
- `AGENTS.md`'s other rules apply unchanged: no secrets, nothing specific to a deployment, no scripts against `api.github.com`.
- A lens SHALL NOT be added before the previous lens has a written retrospective.

## References

- [ADR-004](ADR-004-releases-and-image.md): what the operator alone does at a release
- [ADR-005](ADR-005-toolchain-and-dependencies.md): dependency groups, CI
- [Development guide](../../guides/development.md): the steps of a change
- [Analysis 001](../../analysis/analysis-001-excessive-agency-review.md): the security lens's frame
- [mutmut](https://github.com/boxed/mutmut)
