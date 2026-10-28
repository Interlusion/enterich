# REQ-001: Erpel Core — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

Erpel is an MCP server for ERPNext. It lets one AI agent read an ERPNext company's books and prepare drafts, which a person reviews and submits in ERPNext. It serves MCP over Streamable HTTP as an OAuth resource server: tokens come from an external authorization server (for example Keycloak), and Erpel accepts only those of one configured client and agent identity. It calls ERPNext's REST API with the API key of one ERPNext agent user and holds no other ERPNext credential.

Out of scope: submitting, cancelling, amending or deleting anything; any operation not catalogued in an area spec; issuing tokens or signing users in, including second factors; several agent identities in one instance; browser-based clients calling Erpel directly (no CORS); network access control (source ranges, rate limits per client), which belongs to the deployment.

Key constraints: the ERPNext agent user's permissions are the hard limit, whatever Erpel, the model or the client do; the agent's interface is a fixed list of operations; nothing about one deployment is in Erpel's code, and everything a deployment differs in comes from configuration. Decisions: [ADR-001](../arc42/adr/ADR-001-separate-service-fixed-tools.md), [ADR-007](../arc42/adr/ADR-007-specs-by-accounting-area.md).

This spec holds the product's personas, user stories and terms, and the rules every operation shares. The service around the operations (access, protocol, configuration, logging, limits) is [REQ-002](req-002-service.md); the operations themselves are specified by accounting area, in the area specs listed in the [index](README.md). A deployment's own requirements trace to the IDs of these specs.

## Personas

### REQ-001-P1. The operator

- **Role**: Owns the company's books in ERPNext and decides what the agent may do there: which operations, for which company; connects the agent.
- **Expectations**: Asks the agent about the books and gets drafts that need only a check; can see from Erpel's configuration and tool list what the agent can do.
- **Pain points**: Invoices and journal entries typed by hand; open items looked up across several lists.
- **Underlying fear**: An agent that posts, cancels or deletes something, manipulated by text from outside or by its own mistake; access that can't be stopped quickly; a person's sign-in that hands the agent's tools to someone else.

### REQ-001-P2. The auditor

- **Role**: Checks that the books are complete, unaltered and traceable.
- **Expectations**: For every change, who made it and through which connection.
- **Underlying fear**: (operator's) Agent changes that can't be told apart from a person's.

### REQ-001-P3. The bookkeeper

- **Role**: Reviews the agent's drafts in ERPNext, corrects and submits them. In a small company, the operator.
- **Expectations**: Drafts that need only a check, each with a link, clearly the agent's, with a warning where something looks wrong.
- **Pain points**: Hunting for drafts; finding a duplicate only after submitting it.
- **Underlying fear**: Submitting the agent's mistake unnoticed; the agent overwriting a correction.

### REQ-001-P4. The agent

- **Role**: The AI model that calls Erpel's operations for the operator, through any MCP client.
- **Expectations**: Stable tool names, exact input schemas, results it can rely on, refusals that say what to change.
- **Pain points**: Vague errors that leave it guessing; results the client cuts off without saying so; names that must be exactly right.
- **Underlying fear**: (operator's) The agent taking a remittance text or an incoming invoice as an instruction.

### REQ-001-P5. The deployer

- **Role**: Installs and runs Erpel for a site: the image, its configuration and secrets, the agent user's rights, the authorization server's client. The operator, or an IT provider working for them.
- **Expectations**: One pinned image, configuration from the environment, an exact list of the rights and settings Erpel needs, a health check and logs like any other service.
- **Pain points**: Settings that fail silently; rights lists that drift from what the software needs.
- **Underlying fear**: An Erpel that holds more rights than it needs, or leaks its key.

## User Stories

- REQ-001-P1-1. As the operator, I need the agent to answer questions from the live books so that I don't search lists by hand.
- REQ-001-P1-2. As the operator, I need the agent to prepare and correct drafts of the documents people would otherwise type, so that nobody types them by hand.
- REQ-001-P1-3. As the operator, I need the agent to be unable to post, cancel, delete or discard anything, whatever it is told and whatever the client allows, so that only people post to the books.
- REQ-001-P1-4. As the operator, I need the agent's access to end as soon as I disable its user in ERPNext or in the authorization server.
- REQ-001-P1-5. As the operator, I need to choose which operations my site offers, without changing Erpel's code.
- REQ-001-P1-6. As the operator, I need to trace each change back to the connection and session that caused it.
- REQ-001-P2-1. As the auditor, I need every change made through Erpel recorded under the agent user, distinguishable from people's changes.
- REQ-001-P3-1. As the bookkeeper, I need each draft the agent prepares to come with a link and to be recognisable as the agent's, so that I find and check it quickly.
- REQ-001-P3-2. As the bookkeeper, I need to be warned of likely mistakes in a draft, such as a possible duplicate or a tax template without tax, so that I don't submit them unnoticed.
- REQ-001-P3-3. As the bookkeeper, I need my corrections to a draft to survive the agent's later changes, so that no work is lost.
- REQ-001-P4-1. As the agent, I need exact names, schemas and results, so that I call each operation correctly the first time.
- REQ-001-P4-2. As the agent, I need refusals that name the input and the rule, and a way to narrow a request whose result is too large, so that I can correct myself.
- REQ-001-P4-3. As the agent, I need text written by outsiders marked as such, so that I don't take it for instructions.
- REQ-001-P5-1. As the deployer, I need to configure Erpel from environment variables only, with every mistake named at start, so that one image serves every site.
- REQ-001-P5-2. As the deployer, I need to know exactly which ERPNext rights and authorization-server settings Erpel needs, so that I grant no more.
- REQ-001-P5-3. As the deployer, I need a health endpoint and logs my platform can collect, so that I run and watch Erpel like any other service.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea
- The area specs listed in the [index](README.md) hold the operations. Every requirement of this spec, and its [Operation Conventions](#operation-conventions), apply to every operation; an area spec may tighten them, never loosen them
- A right this spec withholds (submitting, cancelling, amending, deleting, discarding), or a draft type it rules out, can only be granted here, by naming the exception and the area it applies to; the area spec then specifies it
- Every area spec with a create operation defines its duplicate match (REQ-001-PRS-F005)
- Every area spec lists, in a Rights section, the ERPNext rights each of its operations needs (REQ-002-PRS-NF013)

## Terms

- **Agent**: the MCP client acting on behalf of the agent identity, in any client application.
- **Agent identity**: the pair of OAuth client (`azp` or `client_id`) and subject (`sub`) that Erpel is configured to accept.
- **Agent user**: the ERPNext user whose API key Erpel holds.
- **Assigned company**: the one ERPNext company configured for the instance.
- **Operation**: an MCP tool Erpel offers, with a fixed purpose and a fixed input schema; each area spec catalogues its operations, and this spec's [Operation Conventions](#operation-conventions) apply to all of them.
- **Area spec**: a spec listed in the [index](README.md) that holds the operations of one accounting area.
- **Draft**: an ERPNext document with `docstatus` 0.
- **Outside-text field**: a field whose content may have been written by someone outside the company: party names, tax IDs and addresses, item names and descriptions, remarks and terms, supplier references, bank transaction texts, ledger counter-parties. The area catalogues mark each such field.
- **Name input**: an operation input that names an ERPNext record (a document number, a customer, an item, an account).
- **Rejection**: an answer with HTTP 401 or 403 to a request to the MCP endpoint because of its token.
- **Today**: the current date in the configured time zone.

## URS — Functional

#### REQ-001-URS-F001: Read the books

**Description**: The agent SHALL be able to read the records and reports of the assigned company that the area specs list.

**Related User Stories**: REQ-001-P1-1, REQ-001-P1-2, REQ-001-P4-1 | **Rationale**: Answering questions needs the records; preparing a draft needs the exact names of parties, items, accounts, cost centres and tax templates.

#### REQ-001-URS-F002: Prepare drafts

**Description**: The agent SHALL be able to create drafts of the document types the area specs list, in the assigned company, and to change those drafts, and SHALL receive with each draft its number, totals, tax rows where the document has them, and a link to it in ERPNext.

**Related User Stories**: REQ-001-P1-2, REQ-001-P3-1 | **Rationale**: The work the agent saves; the link takes the reviewer to the draft.

#### REQ-001-URS-F003: Never post, cancel, delete or discard

**Description**: No operation SHALL submit, cancel, amend, delete or discard a document, or change a document that is not a draft.

**Related User Stories**: REQ-001-P1-3 | **Rationale**: ERPNext's role refuses submit, cancel, amend and delete to an agent user without those rights, and saving a submitted document needs the submit right too. It can't refuse everything, because some doors check only write or read and never look at `docstatus`:

- `Document.discard` sets a draft to `docstatus` 2 with write alone.
- Purchase Invoice's `block_invoice`, `unblock_invoice` and `change_release_date` change the invoice by `db_set`, a submitted one too, with write alone.
- The v1 `run_doc_method` checks only read before it calls a whitelisted method of a document.

Only a fixed list of operations, without generic method calls, closes these doors (REQ-001-URS-F004, REQ-001-PRS-F006).

#### REQ-001-URS-F004: A fixed list of operations

**Description**: Erpel SHALL offer only the operations catalogued in the area specs; it SHALL NOT offer generic document access, generic method calls or file access.

**Related User Stories**: REQ-001-P1-3, REQ-001-P4-1 | **Rationale**: Generic calls reach the side doors of REQ-001-URS-F003; a fixed list can be reviewed.

#### REQ-001-URS-F005: One company

**Description**: The agent SHALL see and create transactions only in the assigned company, and no draft SHALL take its company from a default.

**Related User Stories**: REQ-001-P1-2, REQ-001-P1-3 | **Rationale**: A site can hold several companies; a draft that takes the site's default company lands in the wrong books.

#### REQ-001-URS-F006: Refusals the agent can act on

**Description**: When ERPNext or Erpel refuses an operation, the agent SHALL receive the reason.

**Related User Stories**: REQ-001-P4-2 | **Rationale**: With the reason the agent corrects a wrong name or a missing field at once; without it, it guesses.

#### REQ-001-URS-F007: No stale writes, no unnoticed duplicates

**Description**: A change to a draft SHALL be refused when the draft changed since the agent read it, and a create that duplicates an existing document SHALL NOT go through unnoticed.

**Related User Stories**: REQ-001-P3-2, REQ-001-P3-3 | **Rationale**: Overwriting a person's edits loses work. A duplicate draft is caught at review, but costs a number from the naming series and the reviewer's time; it arises when an agent retries after a lost answer, in the same conversation or a new one, or enters the same supplier invoice twice.

#### REQ-001-URS-F008: Operations chosen by configuration

**Description**: The operator SHALL be able to limit an instance to a chosen set of operations through configuration, and an operation added in a later Erpel version SHALL NOT appear in such a set by itself.

**Related User Stories**: REQ-001-P1-5 | **Rationale**: A site that wants only reads, or no journal entries, runs a smaller set without a fork, and an update doesn't widen it unnoticed.

#### REQ-001-URS-F009: Warnings reach the reviewer

**Description**: A warning about a draft SHALL be visible to the person reviewing the draft in ERPNext, not only to the agent.

**Related User Stories**: REQ-001-P3-2 | **Rationale**: The bookkeeper reviews in ERPNext and may never see the agent's conversation; a warning that stays there is lost.

## URS — Non-Functional

#### REQ-001-URS-NF001: Safe without client-side approval

**Description**: REQ-001-URS-F003, REQ-001-URS-F004, REQ-001-URS-F005 and REQ-002-URS-NF001 SHALL hold when the client calls every operation without asking a person.

**Related User Stories**: REQ-001-P1-3 | **Rationale**: Clients have been observed calling write tools without asking although set to ask first.

#### REQ-001-URS-NF002: Outside text is data

**Description**: Erpel SHALL return outside-text fields as data, marked as such.

**Related User Stories**: REQ-001-P1-3, REQ-001-P4-3 | **Rationale**: Remittance texts and incoming e-invoices are written by strangers. Draft-only rights contain what a manipulated agent can do; marking lowers the chance.

#### REQ-001-URS-NF003: Results the client can take

**Description**: Each operation's result SHALL stay within a size clients accept, and the agent SHALL be told how to narrow a request whose result would be too large.

**Related User Stories**: REQ-001-P4-2 | **Rationale**: Clients ask for the largest page unprompted, and cut off results above their own limit without saying what was lost.

## PRS — Functional

#### REQ-001-PRS-F001: Read operations

**Description**: Erpel SHALL offer the read operations of the area specs, each calling ERPNext only as its area spec's ERPNext calls table says, and returning at most 100 records per call, with the limit enforced in Erpel.

**Related URS**: REQ-001-URS-F001, REQ-001-URS-F004

**Definition of Done**:

- Each read operation of the area specs works against a fake ERPNext and sends ERPNext only its DocType or report, fields, fixed filters and order as catalogued.
- A `limit` of 101 is refused before any ERPNext call; list results carry `has_more`.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F002: Draft create operations

**Description**: The create operations SHALL send ERPNext exactly the "Sent to ERPNext" fields of their area catalogue, SHALL fill a given tax template's rows from ERPNext where the operation takes a tax template, and SHALL return the draft's number, `modified` timestamp, totals, tax rows where the document has them, and its URL in ERPNext.

**Related URS**: REQ-001-URS-F002, REQ-001-URS-F003, REQ-001-URS-F005

**Definition of Done**:

- For each create operation, the body ERPNext receives equals its catalogue's "Sent to ERPNext" column.
- An input not in the schema, at the top level (`docstatus: 1`, `company`) or in a row, is refused and nothing reaches ERPNext; every published input schema has `additionalProperties: false` at every level.
- A draft created with a tax template carries the template's rows as ERPNext returned them.
- The result carries number, `modified`, totals, tax rows where the document has them, and URL.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F003: Draft update operations

**Description**: The update operations SHALL change only drafts of the assigned company, SHALL send ERPNext exactly the "Sent to ERPNext" fields of their area catalogue for the given inputs, and SHALL replace a draft's rows as a whole when rows are given.

**Related URS**: REQ-001-URS-F002, REQ-001-URS-F003, REQ-001-URS-F005

**Definition of Done**:

- An update of a submitted or cancelled document, or of another company's document, is refused without a write to ERPNext.
- The body ERPNext receives equals the "Sent to ERPNext" column for the given inputs.
- Rows given in an update replace all existing rows: a draft with three rows updated with one row has exactly that row.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F004: Stale updates refused

**Description**: Update operations SHALL require the draft's `modified` timestamp as last read and SHALL be refused, without a change, when the draft's timestamp differs.

**Related URS**: REQ-001-URS-F007

**Definition of Done**:

- An update with an old timestamp is refused with a message saying the draft changed, and the draft is unchanged.
- An update whose draft changes between Erpel's check and its write is refused by ERPNext (`TimestampMismatchError`) and reported the same way.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F005: Possible duplicates refused

**Description**: Before a create, Erpel SHALL look in ERPNext for a document of the assigned company, whoever made it, that matches as the operation's area spec defines. When one matches, Erpel SHALL refuse the create, naming the matching documents and the `allow_duplicate` input. With `allow_duplicate` true, Erpel SHALL create the document and name the matches in `warnings`.

**Related URS**: REQ-001-URS-F007

**Definition of Done**:

- For each create operation, a create sent again after its answer was lost (the first one reached ERPNext) is refused with the first draft's number, and nothing is inserted.
- A create that differs from every existing document in a field of its match goes through without a warning.
- With `allow_duplicate: true`, a matching create goes through and its result names the match in `warnings`.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F006: No generic operations

**Description**: No operation SHALL take a DocType, report name, method name, field list, filter expression or file path as input, no operation SHALL submit, cancel, amend, delete or discard, and none SHALL call a side door of REQ-001-URS-F003.

**Related URS**: REQ-001-URS-F003, REQ-001-URS-F004

**Definition of Done**:

- The published tool list equals the operations of the area specs, held as a snapshot that changes only with a reviewed change to those specs.
- No input schema has a property that accepts a DocType, report, method, field list, filter or path; no ERPNext call Erpel makes uses `docstatus` other than 0 in a body, `run_method` or `run_doc_method`, the submit, cancel, delete or discard routes, or the purchase invoice block and release-date methods.
- Verification: inspection and test.
- Evidence: the tool-list snapshot in Erpel's test suite.

#### REQ-001-PRS-F007: The assigned company from configuration

**Description**: Erpel SHALL set the assigned company on every draft it creates, filter every list of a company's records (transactions, accounts, cost centres, bank accounts, tax templates) and every report by it, and refuse to return or change a transaction of another company.

**Related URS**: REQ-001-URS-F005

**Definition of Done**:

- Every create body carries the configured company; every such list and report call filters by it.
- A get or update of a document whose company differs answers as for a name that doesn't exist (REQ-001-PRS-F009).
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F008: Refusals reported

**Description**: Erpel SHALL return an ERPNext refusal as a tool error carrying the HTTP status, ERPNext's `exc_type` and the first message of `_server_messages`, labelled as ERPNext's message; it SHALL forward no other part of ERPNext's error body (`exc`, `exception`, `_debug_messages`, tracebacks). Erpel's own refusals SHALL be tool errors naming the input and the rule it broke. Every tool error SHALL reach the agent as plain text of at most 300 characters.

**Related URS**: REQ-001-URS-F006, REQ-001-URS-NF002

**Definition of Done**:

- A permission error, a validation error, a link error and a timestamp mismatch from ERPNext each reach the agent with type and message; HTML in the message is removed and entities decoded.
- An error body with a traceback in `exc` yields a tool error without it.
- A refusal without `_server_messages` yields the status and `exc_type`, or for 403 and 404 the text of REQ-001-PRS-F009.
- An input that breaks the schema is refused with the property and rule.
- A message of 2,000 characters from ERPNext, and an input with 50 unknown properties, each reach the agent as at most 300 characters.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F009: Unknown or unpermitted names

**Description**: When ERPNext answers a name input with "not found" or "not permitted", Erpel SHALL say that the name doesn't exist or isn't permitted for the agent user, and name the input.

**Related URS**: REQ-001-URS-F006

**Definition of Done**:

- A 404 and a 403 for a tax template name each produce a tool error naming `taxes_and_charges` and both possible causes.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F010: Name inputs stay names

**Description**: A name input SHALL be 1 to 140 characters, without control or format characters, line or paragraph separators, leading or trailing whitespace, or a `.` or `..` path segment, and SHALL reach ERPNext only as a query parameter, a JSON value or a single URL-encoded path segment.

**Related URS**: REQ-001-URS-F004

**Definition of Done**:

- `../User/Administrator`, `a/./b`, a name with a newline, U+2028 or U+202E, and a 141-character name are refused before any ERPNext call.
- A name with `/`, `%`, `&`, `?`, `#` or spaces, such as `X?run_method=discard` or `a#b`, reaches ERPNext unchanged as one parameter or one encoded segment.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F011: Operations chosen

**Description**: When its configuration lists operations, Erpel SHALL offer and run only those; when it lists none, all operations of the area specs. Erpel SHALL refuse to start when the list names an unknown operation.

**Related URS**: REQ-001-URS-F008

**Definition of Done**:

- With a list of three operations, `tools/list` shows exactly those, and calling another gives an unknown-tool error.
- A misspelt operation name stops Erpel at start with a message naming it.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F012: Tax template without tax

**Description**: A create or update result SHOULD carry a warning when a tax template was given and the draft's tax total is zero.

**Related URS**: REQ-001-URS-F002

**Definition of Done**:

- A draft with a template whose rows have rate 0 and items without an item tax template returns the warning.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F013: No approval in the loop

**Description**: No operation SHALL ask the client for anything (approval, elicitation, sampling) or wait for it; every limit SHALL be enforced in Erpel or ERPNext, and tool annotations SHALL be hints only.

**Related URS**: REQ-001-URS-NF001

**Definition of Done**:

- The end-to-end suite calls every operation, including every refusal case, with a client that never confirms anything.
- No code path sends a request to the client or reads an annotation for a decision.
- Verification: test and inspection.
- Evidence: Erpel's test suite; code review at each release.

#### REQ-001-PRS-F014: Operation conventions

**Description**: Every operation SHALL follow this spec's [Operation Conventions](#operation-conventions): the common inputs and their limits, the result shapes, the states, the way ERPNext is called, and the draft rules.

**Related URS**: REQ-001-URS-F004, REQ-001-URS-F006, REQ-001-URS-NF003

**Definition of Done**:

- An `offset` of 10,001, a quantity with 7 decimal places and a `to_date` before `from_date` are refused naming the input and the rule.
- A `search` for `50%` matches the text `50%` only, not any text starting with `50`.
- Debits of 0.1 and 0.2 against a credit of 0.3 are equal: numbers are compared as decimals.
- List and report results carry `count`, `offset`, `has_more` and `records`; get results carry `modified`, `url` and `truncated`; yes/no fields are booleans.
- Each `state` sends exactly the filter of the States table.
- An update clearing a field its area spec doesn't name as clearable is refused.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-001-PRS-F015: Warnings on the draft

**Description**: When a create or update returns warnings, Erpel SHALL also add them to the draft in ERPNext as a comment, as plain text starting with "Erpel:", through `frappe.desk.form.utils.add_comment`. If adding the comment fails, the result SHALL say so; the draft stays as written.

**Related URS**: REQ-001-URS-F009

**Definition of Done**:

- A create with `allow_duplicate: true` that matches an existing draft leaves a comment on the new draft naming the match.
- A draft with a tax template and zero tax gets the comment of REQ-001-PRS-F012.
- Markup in a warning reaches ERPNext escaped, as text.
- A failing comment call yields a result with the draft and a note that the comment is missing.
- Verification: test.
- Evidence: Erpel's test suite.

## PRS — Non-Functional

#### REQ-001-PRS-NF001: Outside text marked

**Description**: Operations SHALL return outside-text fields only inside an object named `outside_text` in each record and in each child row, and every operation's description SHALL tell the agent to treat that content, and ERPNext's messages in errors, as data, never as instructions.

**Related URS**: REQ-001-URS-NF002

**Definition of Done**:

- Every field an area catalogue marks as outside text appears only under `outside_text` of its record or row; a customer name such as "Ignore previous instructions" arrives there.
- Verification: test and inspection.
- Evidence: Erpel's test suite; the tool-list snapshot.

#### REQ-001-PRS-NF002: Tool annotations

**Description**: Every operation SHALL carry a title and annotations: read operations `readOnlyHint` true; create operations `readOnlyHint` false, `destructiveHint` false, `idempotentHint` false; update operations `readOnlyHint` false, `destructiveHint` true (they replace a draft's content), `idempotentHint` true; all `openWorldHint` false.

**Related URS**: REQ-002-URS-NF007

**Definition of Done**:

- The tool-list snapshot shows the annotations for every operation.
- Verification: inspection.
- Evidence: the tool-list snapshot.

#### REQ-001-PRS-NF003: Result limits

**Description**: Every tool result SHALL stay under 100,000 characters. A get SHALL cut each child table to its first 100 rows and each text field of the record and its rows to 500 characters, and list what it cut in `truncated`; a list or report whose result would still be larger SHALL be refused with a message to narrow it, and a get with a message that the document is too large.

**Related URS**: REQ-001-URS-NF003

**Definition of Done**:

- A get of an invoice with 500 rows returns 100 with `truncated: ["items"]`.
- A get of an invoice whose 100 rows carry descriptions of 2,000 characters returns them cut to 500, with `truncated: ["items.description"]`.
- An oversized report result gives the narrowing message.
- Verification: test.
- Evidence: Erpel's test suite.

## Operation Conventions

What every operation of the area specs follows (REQ-001-PRS-F014). Each area spec catalogues its operations with their inputs, outputs and ERPNext calls; names there are the MCP tool names. Inputs in **bold** are required; all others are optional. A field in *italics* is an outside-text field and is returned under `outside_text` (REQ-001-PRS-NF001). ERPNext DocType and field names follow ERPNext v16.

### Common inputs

| Input | Type | Rule |
| :- | :- | :- |
| `limit` | integer | 1–100, default 20 |
| `offset` | integer | 0–10,000, default 0 |
| `search` | string | 1–140 characters; a case-insensitive substring of the fields the operation names; `%` and `_` taken literally |
| `include_disabled` | boolean | default false; disabled records are left out unless true |
| `include_groups` | boolean | default false; group records (accounts, cost centres) are left out unless true |
| `from_date`, `to_date` | string | ISO date `YYYY-MM-DD`; `from_date` ≤ `to_date` |
| Name inputs | string | REQ-001-PRS-F010 |
| `modified` | string | exactly as Erpel returned it (`YYYY-MM-DD HH:MM:SS.ffffff`), sent back unchanged |
| `allow_duplicate` | boolean | create operations only; default false; REQ-001-PRS-F005 |
| Quantities | number | > 0 and ≤ 10,000, at most 6 decimal places |
| Rates | number | ≥ 0 and ≤ 1,000,000,000, at most 6 decimal places |
| Debit, credit | number | ≥ 0 and ≤ 1,000,000,000, at most 3 decimal places |

Numbers are read as decimals, never as binary floating point. Every operation rejects inputs not in its schema, at every level. Row and quantity limits start low on purpose: raising them later is a minor change, lowering them a breaking one ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).

### Results

- **Lists:** `{count, offset, has_more, records}`, where `records` holds the records in the fixed order of the area spec's ERPNext calls table and `count` is their number.
- **Reports:** as lists, with the report's rows in `records`, paged by Erpel over all rows, and beside them the totals the area spec names.
- **Gets:** the record with `modified`, `url`, its child tables of at most 100 rows each, and `truncated` (usually empty): the names of cut tables, and of cut text fields as `<field>` or `<table>.<field>`.
- **Every record and child row** carries an `outside_text` object, empty when it has no such field.
- **Yes/no fields** (ERPNext's Check fields, stored as 0 and 1) are returned as `true` and `false`.
- **`url`** is the document's form in ERPNext, built as ERPNext v16 builds it: the public URL, `/desk/`, the DocType in lower case with hyphens for spaces, and the name percent-encoded as one segment (`/desk/sales-invoice/SINV-2026-00001`).
- **Creates and updates:** the draft's `name`, `modified`, `status`, `docstatus`, `company`, the further fields its area spec lists, `url`, and `warnings`.

### States

Document `state` inputs map to ERPNext as follows. No `state` means all, unless the area spec sets a default; which states an operation accepts is in its catalogue.

| `state` | Documents | ERPNext filter |
| :- | :- | :- |
| `draft`, `cancelled` | invoices, journal entries, payment entries | `docstatus` 0, 2 |
| `submitted` | journal entries, payment entries | `docstatus` 1 |
| `unpaid` | invoices | `docstatus` 1, `is_return` 0, `outstanding_amount` > 0 (includes overdue) |
| `overdue` | invoices | as `unpaid`, and `due_date` before today |
| `paid` | invoices | `docstatus` 1, `is_return` 0, `outstanding_amount` ≤ 0 |
| `return` | invoices | `docstatus` 1, `is_return` 1 |

### ERPNext calls

Lists use `/api/resource/<DocType>` with the fields of their area catalogue; gets use `frappe.client.get`; reports use `frappe.desk.query_report.run` with `are_default_filters` false, so a site's saved report filters never replace Erpel's. Each area spec's ERPNext calls table names, for its reads and duplicate checks, the DocType or report, the fixed filters and the order. Creates and updates make these further calls: `get_taxes_and_charges` for a given tax template's rows, `frappe.client.get` for the draft before an update, `/api/resource` to write (POST for a create, PUT for an update), and `frappe.desk.form.utils.add_comment` for warnings (REQ-001-PRS-F015), which needs only read on the draft. Every list of a company's records and every report filters by the assigned company (REQ-001-PRS-F007). Erpel leaves out the total row ERPNext appends to a report's rows and computes the totals its area spec names itself. A site that runs a report as a prepared report gets a refusal saying so; Erpel doesn't wait for prepared reports. ERPNext turns a report into a prepared report for good after one run longer than 15 seconds; the configuration guide says how a site prevents that.

### Drafts

- Before a create, the duplicate check of REQ-001-PRS-F005 runs, with the match its area spec defines. Each create operation's description tells the agent, after an error or a timeout, to list the drafts (`state: draft`) before creating again.
- On update, an empty string clears a field only if its area spec names it as clearable (a cleared tax template takes its rows with it); no other field can be cleared.

## Acceptance Criteria Summary

- Each operation of the area specs works against a fake ERPNext and sends ERPNext only its catalogued DocType, fields, filters and order; nothing else is offered.
- No operation submits, cancels, amends, deletes or discards, or changes a non-draft or another company's document; none waits for client approval.
- Stale updates change nothing; a create that duplicates an existing document is refused unless the agent explicitly allows it.
- Refusals reach the agent with ERPNext's reason; names that don't exist or aren't permitted are reported as such.
- Outside-text fields arrive only under `outside_text`.
- The configuration chooses the operations offered.
- Results stay within their limits, and the agent is told how to narrow a request that would exceed them.

## Assumptions

Checked against Frappe and ERPNext v16.52 source:

- An update that sends `modified` is refused with `TimestampMismatchError` when the stored value differs (`Document.check_if_latest`).
- Saving a submitted document needs the submit right (`check_docstatus_transition`).
- ERPNext fills tax rows from a template on insert only when a site setting says so (`add_taxes_from_taxes_and_charges_template`); Erpel therefore fills them itself.
- With only the select right on a DocType, lists return only its search fields; the operations need read (configuration guide).

Not checked yet:

- ERPNext v16's REST API: `/api/resource` for lists, inserts and updates; `frappe.client.get` for a document with its rows; `frappe.desk.query_report.run` for reports; ERPNext's `get_taxes_and_charges` for a template's rows. Erpel calls these only with fixed DocTypes, reports and methods. Report filters and columns are checked against ERPNext v16 when each report operation is built (area specs).
- The deployment gives the agent user a role without submit, cancel, amend, delete, share, import or export, and a User Permission on the assigned company. Erpel neither creates nor checks the role.
- A draft takes the next number of its naming series when created, and an abandoned draft keeps it. Whether that's acceptable is the deployment's decision.
- Two identical creates at the same instant can both pass the duplicate check. One agent works through one conversation in sequence, and a person reviews every draft, so this is accepted.
- Document IDs can contain text a person typed (a customer named after itself); they are returned outside `outside_text` because the agent needs them as inputs.

## Open Questions

None at the moment.
