# ADR-001: A separate service with a fixed tool list, not a Frappe app or a gateway

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |

## Context

An AI agent is to read an ERPNext company's books and prepare drafts, and must be unable to post, cancel or delete, whatever it is told ([REQ-001-URS-F003](../../specs/req-001-core.md#req-001-urs-f003-never-post-cancel-delete-or-discard), [REQ-001-URS-NF001](../../specs/req-001-core.md#req-001-urs-nf001-safe-without-client-side-approval)). Before Erpel, the options were surveyed (October 2026, ERPNext and Frappe v16):

- **MCP apps inside the Frappe bench.** Several exist. Most offer generic create, update and delete, method calls or document actions (submit, cancel), restricted by configuration; some add code or database query tools. In the bench they run with full database access, and they rely on Frappe's OAuth provider.
- **Frappe's OAuth provider as the authorization server** doesn't fit remote MCP clients well: it has no resource indicators or audience binding, its protected resource metadata names the site's origin rather than an MCP URL with a path, and a request without a token to a whitelisted method gets 403, which clients don't take as a cue to sign in.
- **Separate MCP servers for ERPNext** with an external authorization server exist too. They ship 100 and more tools, including submit, cancel and generic method calls, filtered by category or exclusion lists.
- **Frappe's built-in MCP server** (on the v17 development branch, on by default) offers generic document and method tools.
- **Generic MCP gateways** can turn REST calls into tools by configuration. The one that also acts as a resource server for an external authorization server needs an OpenAPI description, which Frappe v16 doesn't provide, and its policies only allow or deny a call. Amount limits, readable ERPNext errors, combining calls (a template's tax rows into an invoice) and refusing stale writes need code.

No published server combined a separate process, an external authorization server, a short fixed tool list and draft-only writes.

## Decision

- **Erpel is its own service**, outside the bench, in its own image. It reaches ERPNext only over the REST API, with the API key of one agent user, and holds no other ERPNext credential.
- **The tool list is fixed and short**, each tool with its own purpose and input schema; reads and writes are separate; writes only create and change drafts. No tool takes a DocType, method, field list or path.
- **An external authorization server signs the agent in**; Erpel is a resource server only ([ADR-003](ADR-003-local-token-check.md)).
- **The protocol comes from the official MCP Python SDK** ([ADR-002](ADR-002-mcp-sdk-stateless-streamable-http.md)).

Ideas taken from other projects: every update carries the document's `modified` timestamp as last read (from an ERPNext MCP tool collection); reads limited to allowlisted DocTypes and reports (from a read-only ERPNext MCP server).

## Alternatives Considered

### Alternative 1: An MCP app in the Frappe bench

**Rejected because**: it runs with full database access, so its own code is the limit rather than the agent user's role; it ties MCP changes to the ERPNext image and its migrations; and it inherits the fit problems of Frappe's OAuth provider.

### Alternative 2: An existing server, restricted by configuration

**Rejected because**: a large generic tool set narrowed by exclusion fails open when a new tool or a configuration mistake slips through; Erpel's limits should be visible in its code and tool list.

### Alternative 3: A generic MCP gateway in front of ERPNext's REST API

**Rejected because**: it still needs a hand-written API description with tool descriptions and schemas, and the checks Erpel needs beyond allow or deny (amounts, balance, company, stale writes, error mapping) would need code anyway.

### Alternative 4: Frappe's built-in MCP server

**Rejected because**: generic tools, and not in v16. Sites on later versions should turn it off (configuration guide).

## Consequences

### Positive

- The agent user's ERPNext role is the hard limit, and Erpel holds nothing that could exceed it.
- The whole interface can be reviewed in one tool list; a change to it is a versioned change ([ADR-004](ADR-004-releases-and-image.md)).
- MCP changes don't touch the ERPNext image or its migrations.

### Negative

- Every operation is code to write and maintain; a new need waits for a release.
- Erpel follows ERPNext's REST API and report output between versions.

## Reconsideration Triggers

Revisit this decision when:

1. Frappe ships an MCP server or OAuth provider that binds tokens to a resource and allows a fixed, reviewed tool list.
2. A gateway can express Erpel's checks (amounts, company, stale writes) as configuration.

## Compliance

- Erpel SHALL reach ERPNext only over its REST API with the agent user's key.
- Erpel SHALL NOT offer generic document access, method calls or file access.

## References

- [REQ-001](../../specs/req-001-core.md) and [REQ-002](../../specs/req-002-service.md): REQ-001-URS-F003, REQ-001-URS-F004, REQ-002-URS-NF003
- [ADR-002](ADR-002-mcp-sdk-stateless-streamable-http.md), [ADR-003](ADR-003-local-token-check.md)
