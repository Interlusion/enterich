# ITEM-004: End-to-end tests against a real ERPNext

| Meta | Value |
| :- | :- |
| **Status** | CANDIDATE |
| **Type** | feature |
| **Origin** | The [backlog](backlog.md)'s line on a test against a real ERPNext; [REQ-002-PRS-NF013](../specs/req-002-service.md#req-002-prs-nf013-rights-listed-and-proven)'s evidence; REQ-001's assumption that the report checks were made against ERPNext v16.52's source |
| **Created** | 2026-10-30 |
| **Author** | loxy (drafted with Claude) |

## Summary

Run Enterich's operations against a real ERPNext v16 site with a seeded company and an agent user holding exactly the rights the area specs list, weekly and on demand. It proves what the tests against `FakeErpnext` can't: that ERPNext answers the way the specs and the fake assume.

## Context / Motivation

`tests/integration` runs the whole path an MCP client takes, against `FakeErpnext`, a model of ERPNext v16's REST API written from ERPNext's source. It proves Enterich right about the model, not the model right about ERPNext. What only a real site shows:

- **Rights** ([REQ-002-PRS-NF013](../specs/req-002-service.md#req-002-prs-nf013-rights-listed-and-proven)): every operation works with exactly the rights its area spec's Rights section lists, and with one listed right removed, the operations that need it fail with ERPNext's permission refusal. Its evidence names this test.
- **The ceiling:** the agent user's key, called directly, not through Enterich, is refused for submit (`frappe.client.submit` and a save with `docstatus` 1), cancel and delete, while two of the doors REQ-001-URS-F003 names stay open as it says: discard with write alone, amend with create alone.
- **Reports:** the filters and columns of Accounts Receivable, Accounts Payable, General Ledger and Trial Balance are the ones the area specs' catalogues name.
- **Duplicates:** the duplicate check finds drafts that people made, not only Enterich's (REQ-001-PRS-F005).
- **Select-only rights:** a DocType the agent may only select arrives without its fields, as the Rights sections say for Journal Entry in the receivable and payable reports.
- **Drift:** a newer ERPNext v16 that changes an answer Enterich relies on fails the weekly run before a deployment updates.

Where the real site answers differently from `FakeErpnext`, the fake is corrected, and Enterich with it if needed.

## Proposal

- **Enterich** runs in-process as in `tests/integration` (`create_app`), with its real HTTP client to the site instead of `FakeErpnext`'s transport. Tokens stay faked (`FakeJwks`): the authorization server isn't under test, and the token check has its own tests.
- **ERPNext** is the official `frappe/erpnext` v16 image, pinned by digest, with MariaDB and Valkey in containers (`tests/e2e/compose.yml`): a new site, ERPNext installed, no scheduler. Only ERPNext, no regional apps: Enterich promises nothing beyond it.
- **Seed data**, made as Administrator through the REST API from the test code, so the data and the names the tests use live in one place, in Python: the setup wizard for the placeholder company the other tests use (`Example GmbH`) with its chart of accounts and fiscal year; items, a customer and a supplier with addresses, tax templates, a bank account; submitted sales and purchase invoices, journal entries, payment entries and bank transactions for the reads and reports; drafts made by Administrator for the duplicate check, by the tests that use them. `bench` only creates the site and installs ERPNext; a seeding step the API can't reach goes there as an exception.
- **The agent user** gets one role holding exactly the rights of the Rights sections (DocType permissions and the report roles), and an API key. The rights come from `RIGHTS` in `tests/e2e/seed.py`, one entry per row of the Rights sections, and a repository check (`tests/repo/test_e2e.py`) fails when the two differ.
- **Tests** in `tests/e2e/`, the end-to-end level of the [development guide](../guides/development.md), skipped unless the site's URL is set, so the default run, the runner's check and the image's test stage stay as they are. A script starts the site locally (`scripts/erpnext-site.sh`) and keeps it running until it removes it; the tests seed it once, so they can run again in seconds, and each run removes the drafts of the runs before it, so none is taken for a duplicate.
- **CI:** a workflow of its own, weekly and started by hand, not on pull requests and not a required check. Each run builds a fresh site: about a minute, plus the image's download. A failure shows on the Actions page.

## Steps

- [x] The site: script, pinned image, the company and the agent user with the rights of RIGHTS (`tests/e2e/seed.py`); locally and in the workflow (`e2e.yml`). About 70 seconds locally on a fresh site, a few seconds on a kept one; the workflow's first run on `main` (2026-10-30) took 3 minutes 8 seconds.
- [x] The reads and reports of each area against the seed, with the catalogues' filters and columns. Every read answered as Enterich expects.
- [x] The drafts: create, update, warnings as comments, the duplicate check with people's drafts. The rate-0 warning needs an item without a price: the seeded invoices gave the other one its price-list rates (Stock Settings' `auto_insert_price_list_rate_if_missing`, on by default).
- [x] The ceiling: submit, cancel and delete refused for the agent's key, and any change to a submitted document; a draft discarded with write alone and a cancelled document amended with create alone, so REQ-001-URS-F003 names the amendment among its doors (history entry).
- [ ] The rights: each listed right removed in turn, and the operations that need it refused.
- [ ] `FakeErpnext` corrected where the real site differs, with the tests that show it.
- [ ] Where the specs and arc42's risks name the test as backlog (REQ-001's assumptions, REQ-002-PRS-NF013, the area specs' report requirements and assumptions), they name the test instead; history entries, since the specs are baselined.

## Open Questions

None. Decided on 2026-10-30: seeding through the REST API, a fresh site in each CI run, and weekly runs besides the manual start.

## Notes

- On this machine the ERPNext, MariaDB and Valkey images take a few GB; remove them after a run (`docker image prune`).
- The rights test removes rights one at a time, which needs ERPNext's permission cache cleared between steps.
- **Faster later, if waiting for the site becomes a nuisance:** a snapshot of the seeded site as two images, MariaDB with the data directory baked in (outside its declared volume) and `frappe/erpnext` with the site's files, so a run starts in seconds. CI keeps them in the Actions cache (`docker save`), keyed by the ERPNext digest and a hash of the seed code, never in GHCR: images are pushed only by the release workflow. A new ERPNext release changes the key, so the weekly drift check still builds anew; the snapshot helps repeated manual runs.
