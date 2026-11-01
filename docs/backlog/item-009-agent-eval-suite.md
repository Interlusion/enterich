# ITEM-009: Agent eval suite

| Meta | Value |
| :- | :- |
| **Status** | IDEA |
| **Type** | feature |
| **Origin** | [Analysis 001](../analysis/analysis-001-excessive-agency-review.md#36-quality-in-operation), finding 6 |
| **Created** | 2026-11-01 |
| **Author** | loxy (drafted with Claude) |

## Summary

A set of fixed cases, each a task for the agent on seeded data with the tool calls it must make and those it must not, run against a real model through Enterich, so that a new model, client or tool description can be judged before a deployment switches to it.

## Context

Enterich's tests prove what Enterich does with a call, not which calls a model makes. Tool descriptions and refusal texts are written for the agent ([REQ-001-P4](../specs/req-001-core.md#req-001-p4-the-agent)), and whether a model follows them, and resists the outside text it reads, changes with each model.

## Conditions

- Cases as data, for example task, seed, expected calls (operation and the inputs that matter), forbidden calls, and the expected end state in ERPNext.
- Injection cases from the start: a customer or supplier named as an instruction, a remittance text in a bank transaction, an incoming invoice text asking for a second draft, a journal entry or `allow_duplicate`; the pass condition is that no forbidden call is made.
- Runs against the end-to-end ERPNext site and an Enterich in front of it; the model and its key come from the environment, never from the repository.
- Not a gate on every pull request (cost, a model's variance): run by hand and before a release that changes tool descriptions, with the pass rate per case recorded per model.

## Open Questions

- Which harness: a small loop of Enterich's own over an LLM API, or an existing eval tool that speaks MCP?
- How many runs per case make a pass rate meaningful, and which rate counts as a pass for an injection case (anything below all?)
- Where results live: in the repository per release, or only in the run's output?
