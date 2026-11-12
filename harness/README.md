# Improvement pipeline

The scripts, schemas and rubrics of the improvement pipeline: agents between deterministic stages, on `auto/` branches only. Why and the rules: [ADR-008](../docs/arc42/adr/ADR-008-improvement-pipeline.md).

## The tests lens

A run lives in `runs/<date>-tests/`.

1. **Inventory:** `uv run python harness/inventory.py harness/runs/<date>-tests` writes the specs' requirements with their Definition of Done items (`requirements.jsonl`), the tests with the requirement IDs they cite (`tests.jsonl`), and the counts (`inventory.json`).
2. **Mutation:** `uv run --group harness python harness/mutation.py harness/runs/<date>-tests [--fresh]` runs mutmut over `src/enterich/` against the unit and integration tests (`[tool.mutmut]` in `pyproject.toml`) and writes the surviving mutants with their diffs (`survivors.jsonl`) and the counts per module (`mutation.json`). CPU only, about half an hour on 8 cores; mutmut keeps its state in `mutants/`, so a second run checks only what changed.
3. **Survey and verify:** the Workflow `improve-tests` (`.claude/workflows/improve-tests.js`), run from Claude Code with the run directory as its argument. Its agents read the run's files and return findings, each with a verdict from another agent; the session writes them to `findings.jsonl`.
4. **Triage:** `uv run python harness/triage.py harness/runs/<date>-tests` checks every record, drops what `suppressions.jsonl` lists, sorts the confirmed findings into fix, proposal and dropped, and writes `report.md`.

The fix stage (one agent per confirmed fix, each on its own `auto/` branch) follows once the first run's report has been reviewed.

## Suppressions

`suppressions.jsonl` holds what the operator decided not to act on, one JSON object per line: `{"key": "<finding key>", "reason": "…"}`. A finding's key is its kind and location, so a suppression outlasts a rerun.
