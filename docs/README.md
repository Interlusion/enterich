# Documentation

## Quick navigation

| I want to … | Read |
| :- | :- |
| Know what Erpel must do, and its tools | [Specs](specs/README.md): REQ-001 core, REQ-002 service, REQ-003 to REQ-007 the operations by area |
| Understand how it fits together | [Architecture](arc42/README.md) |
| Know why it is built this way | [ADRs](arc42/adr/README.md) |
| Configure and run it | [Configuration](guides/configuration.md), [Keycloak](guides/keycloak.md) |
| Review the agent's drafts | [Reviewing drafts](guides/reviewing-drafts.md) |
| Contribute or work on it | [Contributing](../CONTRIBUTING.md), [Development](guides/development.md) |
| Report a vulnerability | [Security policy](../SECURITY.md) |
| Release it | [Releasing](guides/releasing.md) |
| See open work | [Backlog](backlog/backlog.md), [ITEM-001 Going public](backlog/item-001-going-public.md), [ITEM-002 OpenTelemetry](backlog/item-002-opentelemetry.md) |

## Directories

- **`specs/`**: requirement specifications: REQ-001 for the core, REQ-002 for the service, one spec per accounting area for the operations. They are the contract: a new operation or a changed input starts there.
- **`arc42/`**: the architecture, all sections in one file for now; `arc42/adr/` holds the decisions.
- **`guides/`**: how-tos, kept current.
- **`backlog/`**: `backlog.md` for quick items, `item-NNN-*.md` for items with detail, `archive/` for done or rejected ones.

## Document status

| Document | Status |
| :- | :- |
| Specs | Draft until baselined and edited in place until then; after baseline, changes are recorded in a history file next to each (`req-NNN-name.history.md`) |
| ADRs | Proposed until accepted; superseded by new ADRs rather than rewritten |
| Architecture, guides | Kept current with every change they describe |
| Backlog | Living |

## Conventions

- **Generic only.** Docs describe Erpel, never a deployment: placeholders such as `erp.example.com`, `id.example.com`, `Example GmbH`.
- **Plain Markdown links**, so they work on GitHub.
- **Requirement IDs in full:** `REQ-001-PRS-F005`, never `PRS-F005`.
- **The name:** Erpel in prose, like Git; `erpel` where it is an identifier (package, command, repository, image); `ERPEL_` for variables.
- **Source of truth:** the specs for what Erpel must do; the code for what it does. When docs and code disagree, fix one of them in the same change.
- Agent-drafted documents say so under Author.
