# REQ-003: Enterich Master Data — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The operations on master data that serve several accounting areas and are maintained by none of them. The master data here is items. Sales and purchase drafts need exact item codes, and the item's accounts, cost centres and tax templates for the assigned company help the agent fill them in. Read only.

Out of scope: creating or changing items; prices and price lists; stock.

Read [REQ-001](req-001-core.md) first: it holds the personas, user stories and terms, and the rules every operation follows.

## User Stories

The personas (REQ-001-P1 the operator, REQ-001-P3 the bookkeeper and others) are [REQ-001's](req-001-core.md#personas).

- REQ-003-P1-1. As the operator, I need the agent to find the right item and its accounts and tax templates for my company, so that the drafts it prepares use exact codes.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## URS — Functional

#### REQ-003-URS-F001: Read items

**Description**: The agent SHALL be able to find items by code or name and read an item with its defaults and item tax templates for the assigned company.

**Related User Stories**: REQ-003-P1-1 | **Refines**: REQ-001-URS-F001 | **Rationale**: An item's defaults for the company are what a draft row needs.

## PRS — Functional

#### REQ-003-PRS-F001: Item operations

**Description**: Enterich SHALL offer `list_items` and `get_item` as the catalogue below defines them, and `get_item` SHALL return only the assigned company's Item Default row.

**Related URS**: REQ-003-URS-F001

**Definition of Done**:

- An item with Item Default rows for two companies returns only the assigned company's accounts and cost centres.
- Verification: test.
- Evidence: Enterich's test suite.

## Operation Catalogue

REQ-001's [Operation Conventions](req-001-core.md#operation-conventions) apply.

| Operation | Inputs | Returns per record |
| :- | :- | :- |
| `list_items` | `search` (item code, item name), `include_disabled`, `limit`, `offset` | `item_code`, *`item_name`*, `item_group`, `stock_uom`, `is_stock_item`, `disabled` |
| `get_item` | **`item_code`** | as above, plus *`description`*, `item_tax_templates` \[`item_tax_template`, `tax_category`, `valid_from`\], and for the assigned company `income_account`, `expense_account`, `selling_cost_center`, `buying_cost_center` |

### ERPNext calls

| Operations | DocType | Fixed filters | Order |
| :- | :- | :- | :- |
| `list_items`, `get_item` | Item, with its Item Default row for the assigned company and its Item Tax rows | — | `name` |

### Rights

| Operations | ERPNext rights of the agent user |
| :- | :- |
| `list_items`, `get_item` | Item: read |

## Acceptance Criteria Summary

- `list_items` and `get_item` work against a fake ERPNext as catalogued.
- An item's defaults are those of the assigned company only.
- Item names and descriptions arrive only under `outside_text`.

## Assumptions

Checked against ERPNext v16.52 source:

- Item Default rows hold an item's defaults per company (`company`, `income_account`, `expense_account`, `selling_cost_center`, `buying_cost_center`).

Not checked yet:

- The rights in the Rights section are the minimum; the end-to-end test proves them (REQ-002-PRS-NF013).

## Open Questions

None at the moment.
