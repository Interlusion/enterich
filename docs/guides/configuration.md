# Configuration

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: every variable is built; the operations so far are those of master data |

Erpel reads its whole configuration from environment variables at start and refuses to start if one is missing or invalid, naming the variable (spec REQ-002-PRS-NF005). There is no configuration file. Variables are part of the versioned interface ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).

## Variables

### Token check

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ERPEL_RESOURCE_URL` | yes |  | The MCP endpoint exactly as clients enter it, e.g. `https://erp.example.com/mcp`: `https`, lower-case host, no default port, a path without a trailing slash, no query or fragment. Tokens must carry it in `aud`; the metadata's `resource` is this value |
| `ERPEL_ISSUER` | yes |  | The authorization server's issuer, `https`, e.g. `https://id.example.com/realms/example` |
| `ERPEL_JWKS_URL` | yes |  | Its signing keys, `https`, e.g. `https://id.example.com/realms/example/protocol/openid-connect/certs` |
| `ERPEL_CLIENT_ID` | yes |  | The OAuth client the agent's tokens are issued to (`azp` or `client_id`) |
| `ERPEL_SUBJECT` | yes |  | The agent identity's `sub` (for Keycloak, the ID of the user or of the client's service account) |
| `ERPEL_REQUIRED_SCOPES` | no | `openid` | Space-separated, at least one; required in the token and published as `scopes_supported`. Publishing them matters: a client that finds no `scopes_supported` requests every scope the authorization server advertises, and the sign-in fails with `invalid_scope` when the client isn't allowed one |
| `ERPEL_TOKEN_ALGORITHMS` | no | `RS256` | Comma-separated; only RS, PS, ES and EdDSA algorithms |
| `ERPEL_CLOCK_LEEWAY` | no | `5` | Seconds, 0–60 ([ADR-003](../arc42/adr/ADR-003-local-token-check.md)) |

The three URLs may use plain `http` only for a loopback host (tests and local development). Setting up Keycloak for Erpel: [Keycloak guide](keycloak.md).

### ERPNext

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ERPEL_ERPNEXT_URL` | yes |  | Base URL Erpel calls. An `http://` address sends the API key unencrypted: use it only on a network you trust (Erpel logs a warning at start for any host but loopback) |
| `ERPEL_ERPNEXT_HOST` | no | host of `ERPEL_ERPNEXT_URL` | `Host` header sent, for a site served under another name than the address Erpel calls: a host name or IP address, optionally with a port |
| `ERPEL_ERPNEXT_PUBLIC_URL` | yes |  | Base URL people open ERPNext at; used for links in results |
| `ERPEL_ERPNEXT_API_KEY` | yes |  | The agent user's API key (secret) |
| `ERPEL_ERPNEXT_API_SECRET` | yes |  | The agent user's API secret (secret) |
| `ERPEL_COMPANY` | yes |  | The assigned company, exactly as named in ERPNext |

Erpel ignores proxy settings from the environment (`HTTP_PROXY`, `HTTPS_PROXY`) for its ERPNext calls, so no proxy sees the API key.

### Service

| Variable | Required | Default | Meaning |
| :- | :- | :- | :- |
| `ERPEL_TOOLS` | no | all operations | Comma-separated operation names to offer; an unknown name stops Erpel. When set, operations added in later versions stay off until added here |
| `ERPEL_TIMEZONE` | no | `UTC` | IANA time zone name, e.g. `Europe/Berlin`; defines "today" for defaults and the overdue state |
| `ERPEL_HOST` | no | `0.0.0.0` | Listen address |
| `ERPEL_PORT` | no | `8000` | Listen port |
| `ERPEL_LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, for the lines of libraries and the HTTP server; Erpel's own events are always written. No level logs secrets or tokens |

## What the site must provide

Erpel neither creates nor checks the agent user's rights; ERPNext enforces them. The site provides:

- **An agent user** used by nothing else, with an API key and secret.
- **A User Permission** on the assigned company, marked as default.
- **A role without** submit, cancel, amend, delete, share, import or export on any DocType.
- **Never** give the agent user System Manager, Accounts User, Accounts Manager, write on Item Price or on any Settings DocType, or any right on User, Role, Role Profile, User Permission, DocPerm or Custom DocPerm: each would let it post or change the rules it runs under.
- **The rights the offered operations need,** and no more. Each area spec lists them per operation in its Rights section; offer an operation, grant its rights: [master data](../specs/req-003-master-data.md#rights), [order to cash](../specs/req-004-order-to-cash.md#rights), [procure to pay](../specs/req-005-procure-to-pay.md#rights), [record to report](../specs/req-006-record-to-report.md#rights), [bank and cash](../specs/req-007-bank-and-cash.md#rights). Use read where they say read, not only select: with select only, ERPNext returns just a DocType's search fields, so records arrive with fields silently missing.

Adding a permission rule for a DocType in ERPNext replaces its standard rules with the site's own; copy the existing rules first.

- **Reports:** a report operation also needs the agent's role on the report. A standard report can't be saved outside developer mode, so grant the role through Role Permission for Page and Report. Its list of roles replaces the report's own: enter the roles that use the report today as well, or they lose it.

- **No automatic prepared reports:** ERPNext turns a report into a prepared report for good once a run takes longer than 15 seconds, and Erpel then refuses it. For each report Erpel runs (Accounts Receivable, Accounts Payable, General Ledger, Trial Balance), set Disable Prepared Report Automation in the System Console with Commit ticked, since the report form can't save a standard report: `frappe.db.set_value("Report", "Accounts Receivable", "disable_prepared_report_automation", 1)`. A report already turned also needs `prepared_report` set back to 0.

- **Site settings:**

  - Document sharing is on by default and lets any user with share rights pass the agent user further rights: turn it off (System Settings, `disable_document_sharing`).
  - Turn on API request logging (System Settings, `log_api_requests`): it records path, user and method of the agent user's calls in ERPNext, next to Erpel's own log.
  - Where the Frappe version has a built-in MCP endpoint with generic tools, turn it off (`disable_mcp_server`); set it before an upgrade brings the endpoint, so it never opens silently.

## Example

Placeholders only; secrets come from the platform's secret store, never from a file in a repository.

```sh
ERPEL_RESOURCE_URL=https://erp.example.com/mcp
ERPEL_ISSUER=https://id.example.com/realms/example
ERPEL_JWKS_URL=https://id.example.com/realms/example/protocol/openid-connect/certs
ERPEL_CLIENT_ID=erpel-agent
ERPEL_SUBJECT=00000000-0000-0000-0000-000000000000
ERPEL_ERPNEXT_URL=http://erpnext.internal:8080
ERPEL_ERPNEXT_HOST=erp.example.com
ERPEL_ERPNEXT_PUBLIC_URL=https://erp.example.com
ERPEL_COMPANY=Example GmbH
ERPEL_TIMEZONE=Europe/Berlin
ERPEL_ERPNEXT_API_KEY=…
ERPEL_ERPNEXT_API_SECRET=…
```

## Kill switches

In order of speed:

1. **Disable the agent user in ERPNext**, or regenerate its API secret. The next operation fails.
2. **Disable the agent identity at the authorization server**, or revoke its sessions. Operations fail once the current access token expires (its lifetime plus `ERPEL_CLOCK_LEEWAY`), so keep access tokens short-lived. Signing out is not enough: clients hold refresh or offline tokens.
3. **Stop Erpel** or remove its route.

## References

- [REQ-002: Erpel service requirement specification](../specs/req-002-service.md)
- [Keycloak as authorization server](keycloak.md)
- [Architecture: deployment view](../arc42/README.md#7-deployment-view)
