# Changelog

All notable changes to Enterich are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Enterich uses [Semantic Versioning](https://semver.org/) as defined in [ADR-004](docs/arc42/adr/ADR-004-releases-and-image.md). Besides Added, Changed, Deprecated, Removed, Fixed and Security, a release lists **Rights** when the ERPNext agent user needs different rights, and **Configuration** when environment variables change.

## [Unreleased]

## [0.2.0] - 2026-11-01

### Added

- **The MCP Registry:** each release publishes Enterich's entry, `dev.interlusion/enterich`, from `server.json`. The image carries the label `io.modelcontextprotocol.server.name` with that name, which the registry checks. Enterich runs as a service behind an authorization server; the entry is for finding it, not for a client to start it.

### Changed

- A list in which ERPNext held back fields Enterich asked for is refused, naming the DocType and the read right the agent user lacks. Before, with only select on a DocType or a field above the agent's permission level, Enterich returned such fields as null or false (`list_items` said `is_stock_item: false` for a stock item), and a duplicate check missed duplicates.

### Fixed

- `report_general_ledger`'s description said `currency` names only an account's or party's currency, and REQ-006 that it is null otherwise. ERPNext always names the amounts' currency, so Enterich returns the company's currency there, as it did from the start; both now say so.

### Rights

- Fewer rights: the drafts need none on what they only link to (company, currency, units, price list, payment terms, project, cost centres, and a journal entry's accounts, parties and invoices), a sales draft needs only select on Customer, Trial Balance needs no read on Account, and General Ledger needs read on Account only for the `account` given. ERPNext's roles All and Desk User add their own rights to every desk user (configuration guide).
- No hidden fields: don't raise the permission level of a field Enterich returns above the agent's role, and don't mask it. A list without the field is refused, but a get returns it as empty, and a masked value as a placeholder such as `XXXXXXXX` (configuration guide).

## [0.1.0] - 2026-10-30

The first release.

### Added

- **An MCP server for ERPNext** over stateless Streamable HTTP, with 31 tools in five accounting areas, each with a fixed purpose and input schema. The README lists them; `enterich-X.Y.Z-tools.json` with each release holds their full contract.
- **Access by OAuth:** access tokens from an external authorization server, checked by Enterich itself against the server's keys (issuer, audience, client, subject), and protected resource metadata for MCP clients. The Keycloak guide shows a setup.
- **One ERPNext user:** Enterich calls ERPNext's REST API with the API key of a dedicated agent user and nothing else. Whatever Enterich does, that user's role is the upper limit.
- **Master data:** items.
- **Order to cash:** customers, sales invoices, sales tax templates and Accounts Receivable; draft sales invoices, created and updated.
- **Procure to pay:** suppliers, purchase invoices, purchase tax templates and Accounts Payable; draft purchase invoices, created and updated. A supplier's invoice number already recorded is refused.
- **Record to report:** accounts, cost centres, journal entries, General Ledger and Trial Balance; draft journal entries, created and updated, refused unless they balance.
- **Bank and cash:** bank accounts, bank transactions (unreconciled by default) and payment entries.
- **Drafts only:** the agent can create and update drafts but never submit, cancel, amend or delete. A create that matches an existing document is refused unless the agent says it is meant; an update to a draft that changed since it was read is refused. Warnings, such as a rate a pricing rule changed, are added to the draft as a comment starting with "Enterich:" (reviewing-drafts guide).
- **Limits:** long results and texts are cut and marked, request bodies are limited to 1 MiB, ERPNext calls to 30 s and operations to 60 s.
- **Operations:** one JSON line per event, with no keys, secrets or tokens, and `/healthz`.
- **Image:** `ghcr.io/interlusion/enterich:X.Y.Z` for amd64 and arm64, with SBOM, provenance and an attestation to check before deploying (configuration guide).

### Configuration

- Everything comes from environment variables starting with `ENTERICH_`: the authorization server and the token's expected issuer, audience, client and subject; ERPNext's URL, the agent user's API key and secret, and the company; optionally `ENTERICH_TOOLS` to offer only some operations. The configuration guide lists each variable.

### Rights

- The agent user needs read rights for the reads, report rights for the reports, and create and write for the drafts' DocTypes, never submit, cancel, amend or delete. Each area spec's Rights section lists them; the configuration guide says how to grant them.

[0.1.0]: https://github.com/Interlusion/enterich/releases/tag/v0.1.0
[0.2.0]: https://github.com/Interlusion/enterich/compare/v0.1.0...v0.2.0
[unreleased]: https://github.com/Interlusion/enterich/compare/v0.2.0...HEAD
