# Configuration

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: every variable and every operation is built |

Enterich reads its whole configuration from environment variables at start and refuses to start if one is missing or invalid, naming the variable (spec REQ-002-PRS-NF005). There is no configuration file. Variables are part of the versioned interface ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).

## Variables

### Token check

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ENTERICH_RESOURCE_URL` | yes |  | The MCP endpoint exactly as clients enter it, e.g. `https://erp.example.com/mcp`: `https`, lower-case host, no default port, a path without a trailing slash, no query or fragment. Tokens must carry it in `aud`; the metadata's `resource` is this value |
| `ENTERICH_ISSUER` | yes |  | The authorization server's issuer, `https`, e.g. `https://id.example.com/realms/example` |
| `ENTERICH_JWKS_URL` | yes |  | Its signing keys, `https`, e.g. `https://id.example.com/realms/example/protocol/openid-connect/certs` |
| `ENTERICH_CLIENT_ID` | yes |  | The OAuth client the agent's tokens are issued to (`azp` or `client_id`) |
| `ENTERICH_SUBJECT` | yes |  | The agent identity's `sub` (for Keycloak, the ID of the user or of the client's service account) |
| `ENTERICH_REQUIRED_SCOPES` | no | `openid` | Space-separated, at least one; required in the token and published as `scopes_supported`. Publishing them matters: a client that finds no `scopes_supported` requests every scope the authorization server advertises, and the sign-in fails with `invalid_scope` when the client isn't allowed one |
| `ENTERICH_TOKEN_ALGORITHMS` | no | `RS256` | Comma-separated; only RS, PS, ES and EdDSA algorithms |
| `ENTERICH_CLOCK_LEEWAY` | no | `5` | Seconds, 0–60 ([ADR-003](../arc42/adr/ADR-003-local-token-check.md)) |

The three URLs may use plain `http` only for a loopback host (tests and local development). Setting up Keycloak for Enterich: [Keycloak guide](keycloak.md).

### ERPNext

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ENTERICH_ERPNEXT_URL` | yes |  | Base URL Enterich calls. An `http://` address sends the API key unencrypted: use it only on a network you trust (Enterich logs a warning at start for any host but loopback) |
| `ENTERICH_ERPNEXT_HOST` | no | host of `ENTERICH_ERPNEXT_URL` | `Host` header sent, for a site served under another name than the address Enterich calls: a host name or IP address, optionally with a port |
| `ENTERICH_ERPNEXT_PUBLIC_URL` | yes |  | Base URL people open ERPNext at; used for links in results |
| `ENTERICH_ERPNEXT_API_KEY` | yes |  | The agent user's API key (secret) |
| `ENTERICH_ERPNEXT_API_SECRET` | yes |  | The agent user's API secret (secret) |
| `ENTERICH_COMPANY` | yes |  | The assigned company, exactly as named in ERPNext |

Enterich ignores proxy settings from the environment (`HTTP_PROXY`, `HTTPS_PROXY`) for its ERPNext calls, so no proxy sees the API key.

### Service

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ENTERICH_TOOLS` | no | all operations | Comma-separated operation names to offer; an unknown name stops Enterich. When set, operations added in later versions stay off until added here |
| `ENTERICH_TIMEZONE` | no | `UTC` | IANA time zone name, e.g. `Europe/Berlin`; defines "today" for defaults and the overdue state; set it to the site's time zone (System Settings), which ERPNext uses for a draft's posting date |
| `ENTERICH_HOST` | no | `0.0.0.0` | Listen address |
| `ENTERICH_PORT` | no | `8000` | Listen port |
| `ENTERICH_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, for the lines of libraries and the HTTP server; Enterich's own events are always written. No level logs secrets or tokens |

## What the site must provide

Enterich neither creates nor checks the agent user's rights; ERPNext enforces them. The site provides:

- **An agent user** used by nothing else, with an API key and secret, and English as its language: ERPNext answers in the user's language, and Enterich reads report rows whose labels and values it translates.
- **A User Permission** on the assigned company, marked as default.
- **A role without** submit, cancel, amend, delete, share, import or export on any DocType.
- **Never** give the agent user System Manager, Accounts User, Accounts Manager, write on Item Price or on any Settings DocType, or any right on User, Role, Role Profile, User Permission, DocPerm or Custom DocPerm: each would let it post or change the rules it runs under.
- **The rights the offered operations need,** and no more. Each area spec lists them per operation in its Rights section; offer an operation, grant its rights: [master data](../specs/req-003-master-data.md#rights), [order to cash](../specs/req-004-order-to-cash.md#rights), [procure to pay](../specs/req-005-procure-to-pay.md#rights), [record to report](../specs/req-006-record-to-report.md#rights), [bank and cash](../specs/req-007-bank-and-cash.md#rights). Use read where they say read, not only select: with select only, ERPNext returns just a DocType's standard and search fields, so records arrive with fields silently missing.
- **Inherited rights:** ERPNext gives every desk user the roles All and Desk User as well. Their rights come on top of the agent's role: among others select on Item, Company, Currency and UOM, read and write on the addresses and contacts the user made, files, to-dos and tags. None of them posts or changes an accounting document.

Adding a permission rule for a DocType in ERPNext replaces its standard rules with the site's own; copy the existing rules first.

- **Reports:** a report operation also needs the agent's role on the report. A standard report can't be saved outside developer mode, so grant the role through Role Permission for Page and Report. Its list of roles replaces the report's own: enter the roles that use the report today as well, or they lose it.

- **No automatic prepared reports:** ERPNext turns a report into a prepared report for good once a run takes longer than 15 seconds, and Enterich then refuses it. For each report Enterich runs (Accounts Receivable, Accounts Payable, General Ledger, Trial Balance), set Disable Prepared Report Automation in the System Console with Commit ticked, since the report form can't save a standard report: `frappe.db.set_value("Report", "Accounts Receivable", "disable_prepared_report_automation", 1)`. A report already turned also needs `prepared_report` set back to 0.

- **No snapshot reports:** a standard report can be set to run on a copy synced to DuckDB (Snapshot Report on the report); its answer is then only as current as the last sync, and Enterich refuses it. Keep it off for the reports Enterich runs.

- **Site settings:**

  - Document sharing is on by default and lets any user with share rights pass the agent user further rights: turn it off (System Settings, `disable_document_sharing`).
  - For purchase invoice drafts, keep Purchase Order Required and Purchase Receipt Required at No (Buying Settings), or allow the suppliers invoices without them (`allow_purchase_invoice_creation_without_purchase_order`, `allow_purchase_invoice_creation_without_purchase_receipt`): otherwise ERPNext refuses drafts without one at their first save: every draft for a required purchase order, drafts with stock or asset items for a required purchase receipt.
  - Turn on API request logging (System Settings, `log_api_requests`): it records path, user and method of the agent user's calls in ERPNext, next to Enterich's own log.
  - Where the Frappe version has a built-in MCP endpoint with generic tools, turn it off (`disable_mcp_server`); set it before an upgrade brings the endpoint, so it never opens silently.

## Example

Placeholders only; secrets come from the platform's secret store, never from a file in a repository.

```sh
ENTERICH_RESOURCE_URL=https://erp.example.com/mcp
ENTERICH_ISSUER=https://id.example.com/realms/example
ENTERICH_JWKS_URL=https://id.example.com/realms/example/protocol/openid-connect/certs
ENTERICH_CLIENT_ID=enterich-agent
ENTERICH_SUBJECT=00000000-0000-0000-0000-000000000000
ENTERICH_ERPNEXT_URL=http://erpnext.internal:8080
ENTERICH_ERPNEXT_HOST=erp.example.com
ENTERICH_ERPNEXT_PUBLIC_URL=https://erp.example.com
ENTERICH_COMPANY=Example GmbH
ENTERICH_TIMEZONE=Europe/Berlin
ENTERICH_ERPNEXT_API_KEY=…
ENTERICH_ERPNEXT_API_SECRET=…
```

## Verifying an image

Enterich's images are `ghcr.io/interlusion/enterich:X.Y.Z`, one per release, never `latest` ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)). Deploy one by its digest, which the release page names, and check before deploying that Enterich's release workflow built it from the tag:

```sh
gh attestation verify oci://ghcr.io/interlusion/enterich:X.Y.Z@sha256:… \
  --repo Interlusion/enterich \
  --signer-workflow Interlusion/enterich/.github/workflows/image.yml \
  --source-ref refs/tags/vX.Y.Z \
  --deny-self-hosted-runners
```

- `--signer-workflow` is required: the image is built and attested in `image.yml`, a reusable workflow that the release workflow calls, and naming it makes sure no other workflow of the repository made the image. Write the organisation as GitHub does, `Interlusion`: `gh` compares the signer workflow letter by letter, as the attestation's certificate names it.
- `--source-ref` ties the image to the release's tag.
- `gh` reads the image from GHCR; if it asks, sign in with `docker login ghcr.io`. With `--bundle-from-oci` it takes the attestation from the registry instead of GitHub's API.
- The image also carries an SBOM and BuildKit's provenance for each architecture: `docker buildx imagetools inspect ghcr.io/interlusion/enterich:X.Y.Z --format '{{ json .SBOM }}'`.

## Kill switches

In order of speed:

1. **Disable the agent user in ERPNext**, or regenerate its API secret. The next operation fails.
2. **Disable the agent identity at the authorization server**, or revoke its sessions. Operations fail once the current access token expires (its lifetime plus `ENTERICH_CLOCK_LEEWAY`), so keep access tokens short-lived. Signing out is not enough: clients hold refresh or offline tokens.
3. **Stop Enterich** or remove its route.

## References

- [REQ-002: Enterich service requirement specification](../specs/req-002-service.md)
- [Keycloak as authorization server](keycloak.md)
- [Architecture: deployment view](../arc42/README.md#7-deployment-view)
