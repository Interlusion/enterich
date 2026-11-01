<p align="center"><img src="docs/assets/logo.webp" alt="Enterich's logo: a drake in a cap, holding a microphone, with an MCP chain" width="160"></p>

<h1 align="center">Enterich</h1>

An MCP server for ERPNext with hard limits: a short, fixed list of tools, tokens from an external OAuth authorization server, and only the rights of one ERPNext user.

**Status:** v0.2.0. Every operation is tested against a model of ERPNext v16's API, and weekly against a real ERPNext v16 site.

## What it is

- **A separate service**, not a Frappe app. It calls ERPNext's REST API with the API key of a dedicated agent user and holds no other ERPNext credential. Whatever the service does, ERPNext's role for that user is the upper limit.
- **A resource server** for the MCP authorization spec. It serves the protected resource metadata, answers a missing token with 401, and checks every access token itself (issuer, audience, client, subject). Sign-in happens at an external authorization server such as Keycloak.
- **A fixed list of operations**, each with its own purpose and input schema, read and write separated. No generic document access, method calls or file access.
- **Client-neutral.** It speaks plain MCP (Streamable HTTP) and doesn't rely on any client asking before a write.

## What it is not

- Not a general ERPNext API bridge: tools that take a DocType, report name, method name, field list, filter expression or file path as input are out of scope.
- Not a way to post: no tool submits, cancels, amends, deletes or discards a document. The agent prepares drafts; a person reviews and submits them in ERPNext ([reviewing drafts](docs/guides/reviewing-drafts.md)).
- Not affiliated with or endorsed by Frappe Technologies. ERPNext and Frappe are their trademarks.

## Tools

<!-- tools:start -->

Enterich offers 31 tools. A deployment may offer fewer ([`ENTERICH_TOOLS`](docs/guides/configuration.md)); every tool works on one company, within the rights ERPNext gives the agent user.

### Master data ([REQ-003](docs/specs/req-003-master-data.md))

Items.

| Tool | Title | Kind |
| :- | :- | :- |
| `list_items` | List items | read |
| `get_item` | Get item | read |

### Order to cash ([REQ-004](docs/specs/req-004-order-to-cash.md))

Customers, sales invoices, receivables.

| Tool | Title | Kind |
| :- | :- | :- |
| `list_customers` | List customers | read |
| `get_customer` | Get customer | read |
| `list_sales_invoices` | List sales invoices | read |
| `get_sales_invoice` | Get sales invoice | read |
| `list_sales_tax_templates` | List sales tax templates | read |
| `report_accounts_receivable` | Accounts receivable | read |
| `create_draft_sales_invoice` | Create draft sales invoice | create draft |
| `update_draft_sales_invoice` | Update draft sales invoice | update draft |

### Procure to pay ([REQ-005](docs/specs/req-005-procure-to-pay.md))

Suppliers, purchase invoices, payables.

| Tool | Title | Kind |
| :- | :- | :- |
| `list_suppliers` | List suppliers | read |
| `get_supplier` | Get supplier | read |
| `list_purchase_invoices` | List purchase invoices | read |
| `get_purchase_invoice` | Get purchase invoice | read |
| `list_purchase_tax_templates` | List purchase tax templates | read |
| `report_accounts_payable` | Accounts payable | read |
| `create_draft_purchase_invoice` | Create draft purchase invoice | create draft |
| `update_draft_purchase_invoice` | Update draft purchase invoice | update draft |

### Record to report ([REQ-006](docs/specs/req-006-record-to-report.md))

Accounts, cost centres, journal entries, ledger, trial balance.

| Tool | Title | Kind |
| :- | :- | :- |
| `list_accounts` | List accounts | read |
| `list_cost_centers` | List cost centres | read |
| `list_journal_entries` | List journal entries | read |
| `get_journal_entry` | Get journal entry | read |
| `report_general_ledger` | General ledger | read |
| `report_trial_balance` | Trial balance | read |
| `create_draft_journal_entry` | Create draft journal entry | create draft |
| `update_draft_journal_entry` | Update draft journal entry | update draft |

### Bank and cash ([REQ-007](docs/specs/req-007-bank-and-cash.md))

Bank accounts, bank transactions, payments.

| Tool | Title | Kind |
| :- | :- | :- |
| `list_bank_accounts` | List bank accounts | read |
| `list_bank_transactions` | List bank transactions | read |
| `get_bank_transaction` | Get bank transaction | read |
| `list_payment_entries` | List payment entries | read |
| `get_payment_entry` | Get payment entry | read |

<!-- tools:end -->

## Scope

Enterich is maintained for our own use. Contributions are welcome ([contributing](CONTRIBUTING.md)); support isn't promised. Report vulnerabilities privately, as the [security policy](SECURITY.md) describes.

## Documentation

Start at [docs/README.md](docs/README.md). The most important parts:

- [Requirement specifications](docs/specs/README.md): the core, and the operations by accounting area
- [Architecture](docs/arc42/README.md) and [decisions](docs/arc42/adr/README.md)
- [Configuration](docs/guides/configuration.md)

## Licence

[Apache-2.0](LICENSE). Why: [ADR-006](docs/arc42/adr/ADR-006-licence-and-name.md).
