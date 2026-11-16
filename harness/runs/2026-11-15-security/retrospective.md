# Retrospective: the security lens's first run, 2026-11-15

The first run of the security lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)): one survey per promise of `harness/promises.jsonl`, what `SECURITY.md` names as in scope and the rules of `AGENTS.md`, against the surface `harness/surface.py` listed. Its decisions below are proposals until the operator takes them.

## Outcome

| Stage | Result |
| :- | :- |
| Inventory | 14 promises; 37 tools, 9 requests to ERPNext (3 that write), 27 client calls, 9 log calls, 22 settings, 1 silenced security rule, 20 text inputs without a bound |
| Survey | 14 agents, every one answered: 21 findings |
| Verify | 21 verified: 18 confirmed (3 breaches reproduced, 15 unproven), 3 refuted |
| Triage | 15 to fix, 3 proposals; no ratchet |
| Plan | 10 branches that share no test file; the gate's own breach fixed by hand on the harness's branch, the other 14 fixes on 9 branches |
| Fix | 11 committed, 3 refuted as closed by an earlier fix on their branch |
| Review | 10 accepted, 1 rejected (`auto/security-e2e-seed`) |
| Gate | 7 branches passed, the end-to-end tests included and none skipped; `auto/security-integration-return-drafts` waited, since it changes `drafts.py` and `CHANGELOG.md` as the drafts-per-hour fix does, and passed once rebased after that one's merge and reviewed again |
| Pushed | 8 branches by `gate.py --push` |

The three breaches:

1. **Drafts per hour:** creates sent at once all passed the count before any inserted. Fixed with a lock per DocType from the count to the insert, on `auto/security-integration-order-to-cash-drafts`.
2. **ERPNext's MCP endpoint:** the configuration guide closes it with `disable_mcp_server`, which Frappe 16.54 ignores; `enable_mcp` controls it, on by default. A proposal, as a guide changes: drafted on `docs/frappe-mcp-endpoint`.
3. **The pipeline's pushes:** the gate pushed with no secret scan, and CI scans only pull requests and pushes to `main`. Fixed by hand in the gate, test first: CI's gitleaks over every commit and message since the fork.

The other proposals: a blank `ENTERICH_TOOLS` offers no tool, which nothing pins (loosening the check would offer all 37), and REQ-002-URS-NF008 has no Definition of Done and no check.

## Cost

| Workflow | Agents | Tokens |
| :- | -: | -: |
| Survey and verify | 35 | 2.37M |
| Fix and review | 25 | 1.30M |
| All | 60 | 3.67M |

About 0.2M tokens per confirmed finding, against a budget of 14M.

## What went wrong, and what changes

- **A verifier's reproduction quoted a fake secret** in the run's records, which CI's gitleaks flags. Redacted by hand before the push. The verify prompt should say a reproduction names no secret, real or made up, only that one was planted.
- **Three surveys found one gap** (`amended_from` in a return draft, under three promises). The plan put them on one branch, and the first fix closed all three; the other two agents refuted theirs. It cost two agents and no wrong commit. A key per place, not per promise and place, would merge them in triage, but would hide which promises a place keeps: kept as it is.
- **The seed's settings test was rejected:** it checked the seed's own copy of the guide's settings, not the guide, so the wrong `disable_mcp_server` passed it. Its finding stays open for the next fix stage, after the guide's fix.
- **Two code fixes in one file** can't pass the gate in one call. The return drafts' branch was rebased once the drafts-per-hour branch was merged, and both files conflicted. The resolved fix commit was no commit a review had accepted, and the gate refused it, as it should. Another review agent checked the rebased commits (accepted), the record took them with the earlier ones under `rebased`, and the gate passed and pushed the branch. The harness README now names that step.
- **A gitleaks finding needs entropy:** a planted 24-character hex secret passed the scan, a base64 one didn't. The scan narrows the gap; it doesn't close it.

## What worked

- The promises as the vocabulary: every survey had a defined target, and the inventory refuses a scope line of the policy without one.
- Reproduction as the bar for a breach: two of five breach claims fell to it, one of them a behaviour the specs describe.
- The fix workflow's prompts by lens: a breach's test failed on the unchanged code and the fix made it pass, on both code fixes.

## Decisions proposed

1. A verify prompt that forbids quoting a secret, made up or not, in a reproduction.
2. The next security run after the guide's fix and the merges, on what changed since this one; the lens rests when a run confirms no breach.
3. A Definition of Done for REQ-002-URS-NF008, with a check of the repository's content for deployment facts.
