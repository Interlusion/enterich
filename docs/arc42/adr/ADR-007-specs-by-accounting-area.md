# ADR-007: Requirement specs by accounting area, with one core spec

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |

## Context

Erpel's requirements started as one specification: the service, the rules for every operation and the full catalogue of 31 operations, about 1,000 lines. More operations will come, area by area, and the agent is meant to take on more work on its own over time. Whether it may post, for example, may then differ between areas, each with its own limits.

Specs show only the current state; the reasons for a change go into a history file next to the spec. One spec for everything would collect the history of the token check, of banking and of posting rules in one file.

The options are listed under Alternatives. ERPNext's modules don't fit the cut: Sales Invoice, Purchase Invoice, Journal Entry, Payment Entry and Bank Transaction all belong to its Accounts module, while Customer, Supplier and Item sit alone in Selling, Buying and Stock.

## Decision

- **One core spec (REQ-001)** holds the intended use and the shared personas, user stories and terms, and the rules every operation follows, with the conventions for inputs, results, states and ERPNext calls.
- **One service spec (REQ-002)** holds what surrounds the operations: access and the token check, protocol, configuration, logging, limits and health. An agent working on an operation rarely needs it, so it stays out of the core.
- **One spec per accounting area** holds that area's operations, user requirements and catalogue: master data (REQ-003), order to cash (REQ-004), procure to pay (REQ-005), record to report (REQ-006), bank and cash (REQ-007). Each is self-contained, with the same template as REQ-001, and refers to REQ-001 for what all share.
- **Area specs may tighten REQ-001's rules, never loosen them.** Rights REQ-001 withholds, such as submitting, are widened only in REQ-001, by naming the exception and its area; the area spec then specifies it. So autonomy can grow area by area, while every widening stays visible in one place.
- **Placement follows a map:** an operation belongs to the area of its main DocType or report. The map in the [specs index](../../specs/README.md) assigns each one to an area; a new one goes to the area that uses it, or, if several do, to the area in which people create and change it, or else to master data.
- **IDs are written in full** (`REQ-004-PRS-F005`), and with the project code outside this repository (`ERPL-REQ-004-PRS-F005`).

## Alternatives Considered

### Alternative 1: One spec

**Rejected because**: its history would mix every area, and it grows with every operation; splitting it later would renumber accepted IDs that deployments trace to.

### Alternative 2: Specs by ERPNext module

**Rejected because**: almost everything lands in Accounts, while customers, suppliers and items end up alone, apart from the invoices that use them.

### Alternative 3: The service inside the core

The first cut kept the service in REQ-001.

**Rejected because**: the service was more than half of the core, which came to 950 lines, nearly as long as the single spec before. An agent working on one operation loaded more than before the split, mostly requirements it didn't need.

### Alternative 4: A separate product overview as well

**Rejected because**: the personas, stories and terms are short and change together with the operation rules; a further file adds cross-references without shortening any history.

### Alternative 5: A separate product specification next to the technical one

A product-level document (what Erpel does, for whom) as a second source of truth.

**Rejected because**: two authoritative documents that change together drift. Product-facing descriptions are derived from the specs instead, when they're needed (README, website, user documentation), and the specs win.

## Consequences

### Positive

- Each area's history stays local; a change to banking doesn't touch the other specs.
- Autonomy, such as the right to post, can grow area by area: granted in REQ-001 for one area, specified in that area's spec.
- Code and tests can follow the same areas, so spec, module and test share one name.
- An agent working on one operation loads REQ-001 and one area spec, without the service requirements.

### Negative

- Seven specs and an index instead of one spec; a change to a convention can touch several area catalogues.
- Agents must read REQ-001 as well as the area spec; reading only the area spec misses the shared rules.

## Reconsideration Triggers

Revisit this decision when:

1. REQ-001 grows large enough that its parts change at different rates.
2. Operations keep falling between areas, so the placement rule needs exceptions.

## Compliance

- Every operation SHALL be catalogued in exactly one area spec, the one its main DocType maps to.
- An area spec SHALL NOT loosen a requirement of REQ-001.
- Requirement, user story and persona IDs SHALL be written in full.

## References

- [Specs index](../../specs/README.md)
- [REQ-001](../../specs/req-001-core.md)
