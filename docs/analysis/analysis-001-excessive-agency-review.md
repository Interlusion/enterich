# Analysis 001: Security review for excessive agency

| Meta | Value |
| :- | :- |
| **Date** | 2026-11-01 |
| **Status** | Draft |
| **Author** | loxy (drafted with Claude) |
| **Audience** | Maintainers; deployers deciding how to run Enterich |
| **Purpose** | How much room for action Enterich gives an agent that indirect prompt injection may steer, and what to change |

## 1. Executive Summary

The line "drafts only" holds in two layers: Enterich has no route that submits, cancels, amends, deletes or discards, and the agent user's role refuses submit, cancel and delete, proven against a real ERPNext v16 site. The token check is strict. The room a manipulated agent still has lies elsewhere: the update operations change any draft of the company, including drafts a person prepared; every person using an instance shares one agent identity and sees everything the agent user reads; a draft carries no mark of the session or task it came from; party IDs carry outside text without the marking; there is no ceiling on amounts or on the number of drafts; and no eval suite shows how a new model behaves with the tools. Each has a backlog item ([§4](#4-recommendations)).

## 2. Context / Motivation

The [OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/) (3 August 2026) ranks Excessive Agency third, as LLM03:2026, up from sixth ([LLM06:2025](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)), which names its causes as excessive functionality, permissions and autonomy. OWASP's [exploit roundup for Q3 2026](https://genai.owasp.org/2026/10/08/genai-and-agentic-ai-exploit-roundup-q3-2026/) files incidents under LLM01 Prompt Injection and LLM03 together, where text from outside made an agent act with tools and rights it held. Enterich is exactly such a connector: its agent reads text written by customers, suppliers and banks, and holds write rights in the books.

Scope: Enterich v0.2.1 (commit `0ac7115`): `src/enterich/`, the specs REQ-001 to REQ-007, ADR-001 and ADR-003, the configuration, Keycloak and reviewing guides, the security policy, the tests. Facts about ERPNext were checked against Frappe v16.54 and ERPNext v16.51 sources. Nothing was changed during the review. The request is kept in [Appendix A](#appendix-a-the-request); line numbers below refer to the reviewed commit.

## 3. Findings

### 3.1 Drafts only

- **Enterich's writes:** three calls only: insert and update of a resource, and `frappe.desk.form.utils.add_comment` (`src/enterich/erpnext.py:143-161`). Every create sets `docstatus: 0` itself (`tools/order_to_cash.py:267`, `tools/procure_to_pay.py:332`, `tools/record_to_report.py:601`); the input models forbid unknown properties at every level (`shapes.py`, `Inputs`), so neither `docstatus` nor `amended_from` reaches a body.
- **Updates:** checked for company, state and `modified` before the write (`tools/drafts.py:92-111`); a change in between fails in ERPNext with `TimestampMismatchError`, and saving a submitted document needs the submit right.
- **Side doors:** `frappe.client.submit`, `run_doc_method`, `run_method`, discard and the purchase invoice block methods are never called; the test fake refuses and records each ([REQ-001-PRS-F006](../specs/req-001-core.md#req-001-prs-f006-no-generic-operations)).
- **Side effects:** a Comment per draft with warnings. Besides that, ERPNext turns a report into a prepared report for good after a run over 15 s, which the [configuration guide](../guides/configuration.md#what-the-site-must-provide) already covers.
- **ERPNext's layer:** the role without submit, cancel, amend or delete ([configuration guide](../guides/configuration.md#what-the-site-must-provide)), proven in `tests/e2e/test_ceiling.py:71-121`. Two doors only Enterich's code closes: discard with write alone and amend with create alone (`tests/e2e/test_ceiling.py:123-141`, [REQ-001-URS-F003](../specs/req-001-core.md#req-001-urs-f003-never-post-cancel-delete-or-discard)).
- **Gap:** Enterich doesn't check that a deployment's role is set up that way; a role with submit goes unnoticed. Enterich's own code still can't submit, but anyone holding the key could.

### 3.2 Identity and rights

- **Token check** (`auth.py:159-238`, [REQ-002-PRS-NF001](../specs/req-002-service.md#req-002-prs-nf001-token-check)): asymmetric algorithms from a list, keys only from the configured JWKS URL, `exp`, `iat`, `iss`, `aud` and `sub` required (`auth.py:187`), `aud` the resource URL, 5 s leeway, exactly one client and one subject (`auth.py:215-218`), access-token marker, 8 KiB at most.
- **Scopes:** one global list (`app.py:53`), `openid` by default (`config.py:205`), which every sign-in carries, so the scope gates nothing in practice. No scopes per area; which operations exist is decided per instance by `ENTERICH_TOOLS` (`tools/__init__.py:89`).
- **Several people:** one `ENTERICH_SUBJECT` per instance ([ADR-003](../arc42/adr/ADR-003-local-token-check.md)), and several identities in one instance are out of scope ([REQ-001](../specs/req-001-core.md#intended-use)). People using one instance therefore share one identity: no rights and no attribution per person, and each reaches everything the agent user reads (General Ledger, bank transactions with IBANs, payables).
- **Scopes per area don't help here:** with one identity, which optional scopes a token carries is the client's choice, not a property of the person. Separating people needs separate identities: today, separate instances, each with its own agent user and `ENTERICH_TOOLS`.

### 3.3 Provenance

- **In ERPNext:** the agent's drafts carry the agent user as `owner` ([reviewing guide](../guides/reviewing-drafts.md#finding-the-agents-drafts)), and ERPNext's version history records its changes (`track_changes` is on for Sales Invoice, Purchase Invoice and Journal Entry). An "Enterich:" comment is added only when there are warnings (`tools/drafts.py:214`). Nothing on a draft says which session, client or task it came from.
- **Enterich's log:** one `operation` line per call with `sub`, `sid`, the cut arguments and the document's number (`tools/__init__.py:275-295`, [REQ-002-PRS-NF008](../specs/req-002-service.md#req-002-prs-nf008-log)), on standard output; how long it is kept is the platform's business. The JSON-RPC request ID isn't logged. ERPNext's API request log is recommended, not required ([configuration guide](../guides/configuration.md#what-the-site-must-provide)).

### 3.4 Outside data in results

- **Marking:** outside text in an `outside_text` object per record and row; every tool description says to treat it, and ERPNext's messages, as data, never as instructions (`shapes.py:21`, `tools/__init__.py:126`); tested with "Ignore previous instructions" as customer name, item name and `bill_no`.
- **Attachments and incoming invoices:** no operation reads files ([REQ-001-URS-F004](../specs/req-001-core.md#req-001-urs-f004-a-fixed-list-of-operations)). An incoming invoice reaches Enterich only as the agent's inputs (`bill_no`, `remarks`, rows) and comes back as outside text.
- **Lengths:** a get cuts each text field to 500 characters (`shapes.py:159`); lists and reports don't cut fields, only the whole result at 100,000 characters (`shapes.py:183`, `shapes.py:212`). A single bank transaction description can fill most of a list.
- **Gap:** party IDs aren't marked. ERPNext names customers and suppliers by their name by default (Selling Settings "Customer Naming By", Buying Settings "Supplier Naming By"), so `name`, `customer`, `supplier` and `party` carry the same outside text as `customer_name`, outside `outside_text`: in party lists, invoices, the aged reports, the General Ledger, bank transactions and payment entries (`tools/order_to_cash.py:37,55`, `tools/procure_to_pay.py:37,57`, `tools/record_to_report.py:101`, `tools/bank_and_cash.py:43,91`). Names are at most 140 characters.

### 3.5 Write operations

- **Validation:** strict schemas; names of 1 to 140 characters without control or format characters or path segments; quantity, rate and amount bounds (`shapes.py:56-58`); at most 20 rows; remarks up to 1,000 characters; journal rows balanced as exact decimals.
- **Duplicates:** checked by content before each create ([REQ-001-PRS-F005](../specs/req-001-core.md#req-001-prs-f005-possible-duplicates-refused)); the agent itself can pass `allow_duplicate: true` (`tools/drafts.py:81`), and then only a warning comment remains. The check guards against a retry after a lost answer, not against a manipulated agent.
- **Ceilings:** technical ones only: 1e9 per rate or amount and 10,000 per quantity. No business ceiling per draft, and no limit on how many drafts an agent creates in an hour.
- **Updates of others' drafts:** `editable()` checks company, state and `modified`, not the owner (`tools/drafts.py:92-111`). A manipulated agent can change rates, rows, due date, `bill_no` or accounts on a draft a bookkeeper prepared and will submit; ERPNext's version history shows it, but only to someone who looks, and no comment is added unless there are warnings.
- **Errors:** ERPNext's first message, HTML removed, cut to 300 characters, with key and secret replaced; no traceback (`erpnext.py:214-226`); an unexpected failure reaches the agent as a fixed text. Small internals do reach the agent: Frappe's exception names, a variable name in the redirect error (`erpnext.py:187`), permission hints naming DocTypes, and ERPNext messages that often name the agent user's email. They help the agent act and are kept by design.

### 3.6 Quality in operation

No eval suite: no fixed cases of a task with expected and forbidden tool calls to run when the model or client changes. What exists tests Enterich, not a model: the tool-list snapshot (`tests/snapshots/tools.json`), integration tests with a client that confirms nothing, end-to-end tests against ERPNext v16.

### 3.7 Already solved well

A fixed tool list held as a snapshot; drafts only in two layers, proven against ERPNext v16; the token check after RFC 9068 with the subject check against persons' sessions; no master data writes, so no supplier bank details; stale updates refused; the company enforced everywhere; secrets kept out of results and logs; no limit depends on client approval; kill switches documented.

## 4. Recommendations

| # | Severity | Finding | Section | Item |
| :- | :- | :- | :- | :- |
| 1 | High | Updates change drafts a person prepared | [3.5](#35-write-operations) | [ITEM-005](../backlog/item-005-updates-only-own-drafts.md) |
| 2 | Medium | All people share one identity and see everything the agent user reads | [3.2](#32-identity-and-rights) | [backlog](../backlog/backlog.md): guide for several instances; existing item for several identities |
| 3 | Medium | Drafts carry no mark of session or task | [3.3](#33-provenance) | [ITEM-006](../backlog/item-006-provenance-on-every-write.md) |
| 4 | Medium | Party IDs carry unmarked outside text | [3.4](#34-outside-data-in-results) | [ITEM-007](../backlog/item-007-party-ids-as-outside-text.md) |
| 5 | Medium | No ceiling on amounts or on the number of drafts | [3.5](#35-write-operations) | [ITEM-008](../backlog/item-008-write-ceilings.md) |
| 6 | Medium | No eval suite for a model change | [3.6](#36-quality-in-operation) | [ITEM-009](../backlog/item-009-agent-eval-suite.md) |
| 7 | Low | Lists and reports don't cut text fields | [3.4](#34-outside-data-in-results) | [backlog](../backlog/backlog.md) |
| 8 | Low | The deployment's rights aren't checked | [3.1](#31-drafts-only) | [backlog](../backlog/backlog.md) |
| 9 | Low | The default scope `openid` gates nothing | [3.2](#32-identity-and-rights) | [backlog](../backlog/backlog.md) |
| 10 | Info | Error texts name small internals | [3.5](#35-write-operations) | none: kept by design |

Start with ITEM-005: it is small, its spec change is clear, and it closes the most direct route from an injection to a wrong posting. ITEM-005 and ITEM-008 both need the agent user's name, so whichever comes first settles how Enterich learns it.

## 5. Open Questions

- Should the security policy name excessive agency explicitly, for example an update of a draft Enterich didn't create, once ITEM-005 is decided?
- Is a separate instance per group of people an answer deployments accept, or does it make several identities in one instance ([ADR-003](../arc42/adr/ADR-003-local-token-check.md) trigger 3) more urgent?

## Appendix A: The request

The review was asked for in German; translated:

> Do a security review of Enterich (MCP server for ERPNext) focused on "Excessive Agency", that is, too much room for action for the agent. Occasion: in the OWASP Top 10 for LLM Applications (August 2026), Excessive Agency rose to third place. The typical incidents arise from indirect prompt injection together with write rights that are too broad.
>
> Don't change anything yet. Read specs, ADRs and code and check:
>
> 1. Drafts only: is there any path on which a document is submitted, cancelled or amended (docstatus 1 or 2, submit, cancel, amend)? Also check indirect routes such as frappe.client.submit, run_doc_method, method calls, and documents created as a side effect. Is this also secured in ERPNext, that is, does the agent role lack the submit right? Or does it rest on Enterich's code alone?
> 2. Identity and rights: how is the OAuth token checked (signature, issuer, audience, expiry)? Do scopes apply per tool group (Order to Cash, Procure to Pay, Record to Report and so on), or does every valid token get all tools? If several people use Enterich: does each of them reach everything the agent user sees? What would be the smallest sensible step against that?
> 3. Provenance: can every draft in ERPNext be recognised as coming from the agent, and from which task or client? Is there an audit log of the tool calls?
> 4. Outside data in tool outputs: which free-text fields reach the model unfiltered (descriptions, remarks, names of customers and suppliers, contents of attachments, data from incoming invoices)? Are length and fields limited? Do the docs and the tool descriptions make clear that these are data and not instructions?
> 5. Write tools: validation of inputs, protection against duplicates on repeated calls, upper limits (amounts, number of rows), behaviour on errors. Do error messages reveal internals?
> 6. Quality in operation: are there fixed test cases (a prompt or task with expected tool calls) that can be run when the model changes?
>
> Deliver a short report: per point the state with file and line, then the findings sorted by severity. Phrase each proposal so that it fits directly into the backlog as an ITEM. What is already solved well, in one line only.
