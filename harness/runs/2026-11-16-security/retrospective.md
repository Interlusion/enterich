# Retrospective: the security lens's second run, 2026-11-16

The second run of the security lens ([ADR-008](../../../docs/arc42/adr/ADR-008-improvement-pipeline.md)), on what changed since the first run's records (`surface.py --since a0af20a`): 26 files, touching 12 of the 14 promises. The end-to-end site ran ERPNext 16.55.0 on Frappe 16.56.0.

## Outcome

| Stage | Result |
| :- | :- |
| Survey | 12 agents: 15 findings |
| Verify | 15 verified: 12 confirmed (5 breaches reproduced, 7 unproven), 3 refuted |
| Triage | 1 to fix, 11 suppressed by the operator |
| Fix | by hand, no fix workflow: one end-to-end test, one sentence in a spec |

Of the twelve confirmed findings, two concern Enterich and the guide; ten concern the pipeline's own nets: the repository check of REQ-002-PRS-NF014, written that morning, and the gate's secret scan.

- **Fixed:** no test showed that `disable_document_sharing` refuses a share, which could pass the agent user submit past its role. `tests/e2e/test_site_settings.py` now has a user with read, submit and share on Sales Invoice share one with the agent user and get 403; with the switch off, the same share goes through.
- **Stated, not fixed:** a create Enterich gave up on at its time limit can still be written by ERPNext after a later create's count. REQ-001-PRS-F019 says so; the limit is a ceiling against a runaway agent, not an exact count.
- **Suppressed:** the repository check's gaps (hosts after unusual characters, escaped URLs, files not in UTF-8, no planted public IP), the gate's (binary files, the scanner's exit code, a removed scan), a check that the guide's switches equal the seed's, and a second company to show the User Permission refuses. Each reason is in `harness/suppressions.jsonl`.

## Cost

| Workflow | Agents | Tokens |
| :- | -: | -: |
| Survey and verify | 27 | 1.43M |

## What changes

- **The lens rests** until `src/` or the configuration guide changes. Most of what a run finds now are gaps in the nets the last run added, and each fix to a net is new code the next run finds gaps in. The operator judged further work there over-engineering.
- **A net is accepted as a net:** a check against careless mistakes need not be airtight while review and CI's gitleaks stand behind it.
