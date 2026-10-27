# Changelog

All notable changes to Erpel are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Erpel uses [Semantic Versioning](https://semver.org/) as defined in [ADR-004](docs/arc42/adr/ADR-004-releases-and-image.md). Besides Added, Changed, Deprecated, Removed, Fixed and Security, a release lists **Rights** when the ERPNext agent user needs different rights, and **Configuration** when environment variables change.

## [Unreleased]

### Added

- Requirement specifications (REQ-001 core, REQ-002 service, REQ-003 to REQ-007 by accounting area), architecture, ADRs 001–007, guides (including Keycloak as authorization server) and backlog.
- The service without operations: configuration from `ERPEL_*` variables (REQ-002-PRS-NF005), the token check with JWKS cache (REQ-002-PRS-NF001, REQ-002-PRS-NF007), protected resource metadata (REQ-002-PRS-NF002), MCP over stateless Streamable HTTP with an empty tool list (REQ-002-PRS-NF003), the JSON log with `start`, `rejection`, `jwks` and `error` events (REQ-002-PRS-NF008, REQ-002-PRS-NF009), the 1 MiB body limit (REQ-002-PRS-NF011) and `/healthz` (REQ-002-PRS-NF012).
- Container image (runtime and test stages, amd64 and arm64), CI and Dependabot.
- The ERPNext client: the agent user's key only, the configured Host, no cookies, redirects or proxies (REQ-002-PRS-NF006), 30 s per call and 10 MiB per answer (REQ-002-PRS-NF011), ERPNext's refusals as plain text (REQ-001-PRS-F008).
- REQ-001's conventions for every operation: strict input schemas, name inputs, literal search, outside text apart, child tables cut at 100 rows, results under 100,000 characters, the 60 s operation limit, the `operation` log line, `ERPEL_TOOLS`.
- Master data: `list_items` and `get_item` (REQ-003).

### Rights

- `list_items`, `get_item`: Item read (REQ-003's Rights section).
