# ADR-002: Official MCP Python SDK, stateless Streamable HTTP

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich serves remote MCP clients over the internet and acts as an OAuth resource server ([REQ-002-URS-NF002](../../specs/req-002-service.md#req-002-urs-nf002-standard-mcp-sign-in)). It needs the MCP protocol, the protected resource metadata (RFC 9728) and the 401 handling that starts a client's sign-in. Writing these by hand means following every protocol revision ourselves.

A throwaway spike before Enterich ran the official MCP Python SDK 2.3.0 (`MCPServer` with `AuthSettings` and a custom token verifier) against a hosted MCP client and Keycloak, and passed. It showed:

- The SDK serves the metadata and the 401 with `resource_metadata` from `AuthSettings`; `required_scopes` becomes `scopes_supported`.
- In stateless mode the SDK answers GET on the MCP path with an SSE stream that never carries anything and outlives the token.
- Clients drop the Authorization header when a redirect leads to another origin, for example from a trailing slash to an `http://` URL behind a TLS proxy. Exactly one path, without redirects, avoids the case.
- The SDK's DNS rebinding protection checks Host and Origin; what Origin a hosted client's backend sends is not documented.

Reading the SDK 2.3.0 source while writing the spec showed more:

- The argument model the SDK builds for a tool ignores extra properties instead of refusing them, and the published schema doesn't forbid them.
- The SDK serves several protocol revisions: 2024-11-05 to 2025-11-25 with an `initialize` handshake, and 2026-07-28 as a single exchange.
- Its authentication middleware runs the token verifier for every request that carries a bearer header, on every path; a missing token and a missing scope are decided later, without the verifier.

## Decision

- **Python with the official MCP Python SDK**, pinned exactly ([ADR-005](ADR-005-toolchain-and-dependencies.md)). The SDK provides the protocol, the metadata route and the bearer middleware; Enterich provides the token verifier ([ADR-003](ADR-003-local-token-check.md)) and the tools.
- **Streamable HTTP, stateless, JSON responses.** No MCP sessions, no SSE streams, no server-to-client requests. Any process can answer any request, so Enterich scales and restarts without losing state.
- **A thin ASGI wrapper in front of the SDK** does what the SDK doesn't:
  - answers every method but POST on the MCP path, OPTIONS included, with 405 and `Allow: POST`, before the token check (the transport allows 405 for GET; Enterich offers no CORS, so browser-based clients are out of scope);
  - refuses bodies over 1 MiB (the SDK's own limit is 4 MiB);
  - serves `/healthz` itself, so probes never reach the SDK's middleware;
  - writes the `rejection` log line from the response status of the MCP path, which covers every cause of a 401 or 403.
- **Exactly one path**, no slash redirects.
- **Protocol revisions:** those the pinned SDK serves. Tests cover 2025-06-18, 2025-11-25 and 2026-07-28; an SDK update that adds or drops a revision is a release note.
- **No Origin check (DNS rebinding protection off).** The MCP transport says servers must validate Origin to prevent DNS rebinding. Enterich departs from that on purpose: rebinding attacks a server that trusts the browser's network position or cookies, and Enterich trusts neither; every request needs a bearer token that a page on another origin doesn't have. Hosted clients' backends send undocumented Origin values or none, so an allowlist would make Enterich client-specific (spec REQ-002-PRS-NF004). The deployment routes only Enterich's host to it.
- **uvicorn** as the ASGI server, without proxy headers (Enterich builds no URL from request headers) and without its server header.
- **Tools as typed Python functions** with pydantic input models; the SDK derives the JSON schemas. Enterich replaces the SDK's argument model with one that forbids extra properties and publishes `additionalProperties: false`, at the top level and in every row model.

## Alternatives Considered

### Alternative 1: TypeScript SDK

**Rejected because**: the spike and its token checks are in Python, and ERPNext users who might read or extend Enterich mostly know Python.

### Alternative 2: Stateful Streamable HTTP with sessions

Sessions allow server-to-client notifications and resumable streams.

**Rejected because**: Enterich needs neither; sessions would need sticky routing or shared storage, and a session outlives the token that opened it.

### Alternative 3: Our own minimal MCP implementation

**Rejected because**: following protocol and authorization revisions that clients adopt is the main maintenance cost; the SDK carries it.

### Alternative 4: An MCP framework on top of the SDK (FastMCP 2 and similar)

**Rejected because**: another dependency between Enterich and the protocol, with its own auth layer and release pace; Enterich uses little beyond tools.

## Consequences

### Positive

- Protocol and metadata handling come from the reference implementation.
- No state: any instance answers, restarts lose nothing.

### Negative

- Enterich follows the SDK's major versions; a breaking SDK release needs a rework and a test against real clients.
- The SDK's API names (`MCPServer`, `AuthSettings`) are internal to Enterich but appear in its code, so an SDK upgrade touches several modules.

## Reconsideration Triggers

Revisit this decision when:

1. Enterich needs server-to-client messages (progress, elicitation, sampling).
2. The SDK drops stateless mode or JSON responses.
3. A client Enterich must serve requires SSE responses.
4. A client Enterich must serve runs in a browser and needs CORS.
5. The MCP transport's Origin rule changes, or an attack on a bearer-only server through Origin becomes known.

## Compliance

- Enterich SHALL keep no MCP session state between requests.
- The MCP path SHALL answer POST only and SHALL NOT redirect.
- Every tool's input schema SHALL forbid extra properties.
- Enterich SHALL use the SDK's metadata and bearer handling, not a copy.

## References

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP transports: Streamable HTTP, 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [RFC 9728: OAuth 2.0 Protected Resource Metadata](https://www.rfc-editor.org/rfc/rfc9728)
- [REQ-001](../../specs/req-001-core.md) and [REQ-002](../../specs/req-002-service.md): REQ-002-URS-NF002, REQ-001-PRS-F002, REQ-002-PRS-NF002, REQ-002-PRS-NF003, REQ-002-PRS-NF004, REQ-002-PRS-NF009
