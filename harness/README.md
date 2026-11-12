# Improvement pipeline

The scripts, schemas and rubrics of the improvement pipeline: agents between deterministic stages, on `auto/` branches only. Why and the rules: [ADR-008](../docs/arc42/adr/ADR-008-improvement-pipeline.md).

## The tests lens

A run lives in `runs/<date>-tests/`.

1. **Inventory:** `uv run python harness/inventory.py harness/runs/<date>-tests` writes the specs' requirements with their Definition of Done items (`requirements.jsonl`), the tests with the requirement IDs they cite (`tests.jsonl`), and the counts (`inventory.json`).
2. **Mutation:** `uv run --group harness python harness/mutation.py harness/runs/<date>-tests [--fresh]` runs mutmut over `src/enterich/` against the unit and integration tests (`[tool.mutmut]` in `pyproject.toml`) and writes the surviving mutants with their diffs (`survivors.jsonl`) and the counts per module (`mutation.json`). CPU only, about half an hour on 8 cores; mutmut keeps its state in `mutants/`, so a second run checks only what changed.
3. **Survey and verify:** the Workflow `improve-tests` (`.claude/workflows/improve-tests.js`), run from Claude Code with the run directory as its argument. Its agents read the run's files and return findings, each with a verdict from another agent; the session writes them to `findings.jsonl`.
4. **Triage:** `uv run python harness/triage.py harness/runs/<date>-tests` checks every record, sets aside what `suppressions.jsonl` lists, sorts the confirmed findings into fix, proposal and dropped, and writes `report.md`.

Triage also writes `fixes.jsonl`, the fix stage's input: each fix with its key, its branch's slug and its mutants' diffs.

5. **Fix:** the Workflow `improve-tests-fix` (`.claude/workflows/improve-tests-fix.js`), with the run directory, the base branch, the commit holding the run and the keys and slugs of `fixes.jsonl` as its arguments; each agent reads its record from there. One agent per fix, in a worktree of its own, writes the test on `auto/tests-<slug>`, shows it red against the mutant or a break, and commits it (`test:`, then a `fix:` only if the code was wrong). Another agent redoes the red check and reviews the branch. Nothing is pushed.
6. **Gate:** `E2E_ERPNEXT_URL=… uv run python harness/gate.py harness/runs/<date>-tests auto/tests-… [--push]` refuses a branch that isn't `auto/`, doesn't start with a `test:` or changes what ADR-008 forbids, runs every check in a worktree of the branch, the end-to-end tests included (the site: `scripts/erpnext-site.sh up`), and writes `gates.jsonl`. With `--push`, it pushes the branches that passed. The operator opens and merges their pull requests.

## Suppressions

`suppressions.jsonl` holds what the operator decided not to act on now, one JSON object per line: `{"key": "<finding key>", "reason": "…"}`, and `"backlog": "item-NNN-….md"` when a backlog item will take it up. Triage counts a finding with a backlog item as tracked while the item's file is in `docs/backlog/`; once it is archived, the finding comes back. One without stays suppressed.

Triage gives each finding its key: a mutant gap's lowest mutant id (`mutant-gap:enterich.shapes.x_page__mutmut_9`), since one function can have several gaps; else the kind and location (`dod-gap:req-001-core.md#REQ-001-PRS-F014 item 3`, `weak-test:tests/…::test_…`). A key outlasts a rerun as long as the code or item it names doesn't change; triage refuses two records with one key.
