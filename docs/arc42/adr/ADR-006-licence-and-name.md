# ADR-006: Apache-2.0, and a name without ERPNext or Frappe

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich is to be published so that other ERPNext sites can run it. ERPNext and Frappe are GPL-licensed. Enterich imports no Frappe or ERPNext code: it is a separate program that talks to ERPNext over HTTP ([ADR-001](ADR-001-separate-service-fixed-tools.md)).

Frappe's trademark policy requires permission to use "ERPNext" in a project or product name, and grants it only to non-commercial projects. Enterich is published by a company, so it doesn't qualify.

## Decision

- **Apache-2.0** for Enterich.
- Our reading is that a separate program talking to ERPNext over its REST API is not a work based on ERPNext, so ERPNext's GPL doesn't extend to Enterich. This is our reading, not legal advice.
- Enterich stays a separate program: it imports no Frappe or ERPNext code and copies none.
- **The names "ERPNext" and "Frappe" stay out of the project, package and image names.** Descriptions may say what Enterich works with ("an MCP server for ERPNext"), and the README states that Enterich is not affiliated with or endorsed by Frappe Technologies.
- **Spelling:** Enterich in prose, as Git is; `enterich` wherever the name is an identifier (package, command, repository, image); `ENTERICH_` for environment variables.

## Alternatives Considered

### Alternative 1: MIT

**Rejected because**: Apache-2.0 is as permissive and adds an explicit patent grant.

### Alternative 2: AGPL-3.0

It would oblige anyone who offers a changed Enterich as a hosted service to publish their changes.

**Rejected because**: it would deter the sites and service providers that Enterich is meant for.

## Consequences

### Positive

- Anyone can run, change and offer Enterich, with a patent grant from its contributors.

### Negative

- Changes made by others need not come back.

## Reconsideration Triggers

Revisit this decision when:

1. Enterich needs to import or copy Frappe or ERPNext code.
2. Frappe's trademark policy changes.

## Compliance

- Enterich SHALL NOT import or copy Frappe or ERPNext code.
- No project, package or image name SHALL contain "ERPNext" or "Frappe".
- New dependencies SHALL have licences compatible with Apache-2.0 (backlog: licence check in CI).

## References

- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [ERPNext trademark policy](https://github.com/frappe/erpnext/blob/develop/TRADEMARK_POLICY.md)
- [`LICENSE`](../../../LICENSE)
