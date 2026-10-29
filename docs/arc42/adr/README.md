# Architecture Decision Records

Decisions about Enterich. The architecture they shape is in the [arc42 overview](../README.md).

| ADR | Title | Status |
| :- | :- | :- |
| [ADR-001](ADR-001-separate-service-fixed-tools.md) | A separate service with a fixed tool list, not a Frappe app or a gateway | Accepted |
| [ADR-002](ADR-002-mcp-sdk-stateless-streamable-http.md) | Official MCP Python SDK, stateless Streamable HTTP | Accepted |
| [ADR-003](ADR-003-local-token-check.md) | Local JWT check for one agent identity, 5 s clock leeway | Accepted |
| [ADR-004](ADR-004-releases-and-image.md) | SemVer tags, immutable, one multi-arch image per release | Accepted |
| [ADR-005](ADR-005-toolchain-and-dependencies.md) | Python with uv: lock with hashes, Dependabot, pinned base image and Actions | Accepted |
| [ADR-006](ADR-006-licence-and-name.md) | Apache-2.0, and a name without ERPNext or Frappe | Accepted |
| [ADR-007](ADR-007-specs-by-accounting-area.md) | Requirement specs by accounting area, with one core spec | Accepted |

New ADRs take the highest number + 1 and start as Proposed. An ADR is Accepted when the maintainer accepts it, and is superseded by a new ADR rather than rewritten. Agent-drafted ADRs say so under Author.
