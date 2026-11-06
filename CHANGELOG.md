# Changelog

All notable changes to Enterich are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and Enterich uses [Semantic Versioning](https://semver.org/) as defined in [ADR-004](docs/arc42/adr/ADR-004-releases-and-image.md). Besides Added, Changed, Deprecated, Removed, Fixed and Security, a release lists **Rights** when the ERPNext agent user needs different rights, and **Configuration** when environment variables change.

## [Unreleased]

### Added

- **Payment entry drafts:** `create_draft_payment_entry` and `update_draft_payment_entry` draft a payment received from a customer or made to a supplier through one of the company's bank accounts, allocated to the party's open invoices. Enterich refuses an allocation to an invoice that isn't the party's, submitted and open, or above what is outstanding or paid, and a bank reference (`reference_no`) already recorded for the party unless the agent allows it. A part not allocated, which ERPNext books as an advance, and a bank account in another currency than the party's account are named in `warnings`. Cash accounts, internal transfers, refunds and deductions such as a discount aren't drafted. The limit of drafts per hour counts payment entries on their own.
- **Return drafts:** `create_draft_sales_return` and `update_draft_sales_return` draft a credit note against a submitted sales invoice, `create_draft_purchase_return` and `update_draft_purchase_return` a debit note against a submitted purchase invoice, with the supplier's credit note number as `bill_no`. ERPNext's own return of the invoice gives the party, rates, accounts and taxes; the agent returns everything not yet returned or chosen items and quantities, never more than is left. A second draft return against the same invoice, or a credit note number already recorded for the supplier, is refused unless the agent allows it. An invoice with a fixed discount or charge (such as freight) is returned only whole, as ERPNext's return credits those amounts in full. Returns of POS invoices, of invoices that updated stock, were paid on entry or are on hold, and credit notes without returned items aren't drafted. Returns count towards the limit of drafts per hour with their invoices.
- **`add_deduct_tax` in purchase draft results:** the tax rows of the purchase invoice and return drafts say whether a row is added or deducted, as `get_purchase_invoice`'s do (REQ-005).

### Changed

- **Each write leaves its origin on the draft:** every create and update adds one comment starting with "Enterich:" that names the operation and a call ID, for an update also the inputs it was given, followed by any warnings. Before, a draft got a comment only with warnings. The `operation` log line carries the same `call`, and the client's JSON-RPC `request_id`, so the comment leads to the log line and its session; an `error` line carries the `call` too (REQ-001-PRS-F015, REQ-002-PRS-NF008).
- `update_draft_sales_invoice` and `update_draft_purchase_invoice` refuse a return draft, naming the return's update operation: their rows would break the return's link to the invoice.

### Fixed

- **ERPNext answers in English on every site:** Enterich sends `Accept-Language: en` on each call. For a request with an API key, ERPNext takes the language from the request or System Settings, not from the agent user, so a site with another system language answered in it: messages, the General Ledger's `party_type` and other translated report values, and the texts ERPNext writes on a draft, such as a journal entry's "Reference #… dated …" remark, which are now English. The site needs the Language English enabled, as it is by default (REQ-002-PRS-NF006).
- **VAT rates in tax rows:** the descriptions of the invoice gets and of the invoice and return drafts say that a tax row's `rate` is the rate saved on it: an item with an item tax template is taxed at that template's rate on the rows whose accounts it lists, or not by such a row, so the tax is in `tax_amount`; on purchase invoices, a row with `add_deduct_tax` Deduct is subtracted (REQ-001 Results).
- **No zero-tax warning for reverse charge:** the warning that a given tax template brought no tax comes only when every tax row is 0, not when Add and Deduct rows cancel out (REQ-001-PRS-F012).

### Rights

- **Payment Entry:** read, create and write only if creator for the new operations, with select on Account, read on Bank Account, and read on Customer and Sales Invoice for a customer's payment, Supplier and Purchase Invoice for a supplier's (REQ-007). Write only if creator goes on Payment Entry too, in the second role of the configuration guide.
- **Returns:** the return operations need the rights of the invoice drafts on Sales Invoice or Purchase Invoice (read, create, write only if creator), with read on Address and Item, select on Account, and select on Customer for a credit note or read on Supplier for a debit note (REQ-004, REQ-005). No tax template right is needed.
- Fewer rights: the sales and purchase drafts need only select on Account, not read.

## [0.3.0] - 2026-11-03

### Added

- **A limit of drafts per hour:** with `ENTERICH_MAX_DRAFTS_PER_HOUR` set, `create_draft_sales_invoice`, `create_draft_purchase_invoice` and `create_draft_journal_entry` count the documents of their type the agent user created in the assigned company in the last hour, and refuse a create at the limit without writing, saying that the operator sets it. A misled or looping agent then can't bury the reviewers in drafts. Documents a person created don't count. Unset, nothing changes.

### Changed

- **Updates only on the agent's own drafts:** `update_draft_sales_invoice`, `update_draft_purchase_invoice` and `update_draft_journal_entry` change only drafts the agent user created, and refuse a draft another user created without writing to it, so that an agent misled by outside text can't rewrite a draft a person prepared. A draft of the agent's that a person then edited can still be updated, with its new `modified`. Enterich asks ERPNext once, at the first update, which user its key belongs to (`frappe.auth.get_logged_user`); no right is needed for that.

### Rights

- **Write only if creator** on Sales Invoice, Purchase Invoice and Journal Entry: take write from the agent's role and give the agent user a second role holding only write with Only If Creator on these DocTypes (configuration guide). ERPNext then refuses the agent user's key a change to, or a discard of, a draft a person created, as Enterich does. Enterich works with the old rights too.

### Configuration

- `ENTERICH_MAX_DRAFTS_PER_HOUR`, optional: the most drafts of each type the agent user may create in an hour, from 1 to 1000. Unset, there is no limit. It counts the hour in `ENTERICH_TIMEZONE`, so set that to the site's time zone, as the configuration guide already asks.

## [0.2.1] - 2026-11-01

### Fixed

- **The MCP Registry:** v0.2.0's release didn't publish Enterich's entry, because the release workflow didn't pass the registry's key to the job that publishes it. 0.2.1 is the first version in the MCP Registry, as `dev.interlusion/enterich`. Enterich itself is unchanged from 0.2.0.

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
[0.2.1]: https://github.com/Interlusion/enterich/compare/v0.2.0...v0.2.1
[0.3.0]: https://github.com/Interlusion/enterich/compare/v0.2.1...v0.3.0
[unreleased]: https://github.com/Interlusion/enterich/compare/v0.3.0...HEAD
