# Development

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: everything below is built except `python -m tests.fakes` (the fakes run in tests only) |

## Repository layout

```
src/enterich/
  __main__.py        entry point: python -m enterich
  config.py          environment variables, validation
  app.py             ASGI assembly: SDK app, POST-only and size limit, healthz
  auth.py            token verifier, JWKS cache
  erpnext.py         REST client, error mapping, name encoding
  shapes.py          shared input types, paging, outside_text
  log.py             JSON-lines logging
  tools/             one module per accounting area, named like its spec:
                     master_data, order_to_cash, procure_to_pay,
                     record_to_report, bank_and_cash; drafts.py holds
                     what every draft operation shares, invoicing.py
                     the reads the sales and purchase side share
tests/
  unit/              per module
  e2e/               Enterich against a fake JWKS and a fake ERPNext, named
                     by area like tools/, an area's drafts in their own
                     module (test_order_to_cash_drafts.py)
  fakes/             the fakes, recording every request
  snapshots/         tools.json: the published tool list
  readme.py          the README's tool list, from tools.json and the specs index
docs/                specs, architecture, ADRs, guides, backlog
scripts/             check-links.sh: the Markdown link check;
                     check-workflows.sh: actionlint and zizmor;
                     changelog.py: a version's release notes;
                     image_index.py: the dry run's check of the image
AGENTS.md            rules for coding agents; CLAUDE.md imports it
CONTRIBUTING.md, SECURITY.md
Dockerfile           build, runtime and test stages
pyproject.toml, uv.lock, .python-version
.github/workflows/   ci.yml; release.yml with image.yml (releasing guide)
.github/actionlint/, .github/gitleaks/, .github/lychee/
                     the images CI runs, pinned in a Dockerfile each
.github/dependabot.yml
.github/ISSUE_TEMPLATE/, pull_request_template.md, CODEOWNERS
lychee.toml          the link check's settings
```

Why this toolchain: [ADR-005](../arc42/adr/ADR-005-toolchain-and-dependencies.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs the Python version named in `.python-version`.

```sh
uv sync --locked           # creates .venv from uv.lock, with dev tools
uv run pytest              # all tests, no network, no ERPNext needed
uv run ruff check && uv run ruff format --check
uv run mdformat --check .  # Markdown; without --check it formats
scripts/check-links.sh     # no wiki-links; local links and #anchors resolve (Docker)
scripts/check-workflows.sh # actionlint with shellcheck (Docker), zizmor
uv run basedpyright
uv run enterich            # starts Enterich; needs the ENTERICH_* variables
```

Run Enterich locally against the fakes:

```sh
uv run python -m tests.fakes   # fake JWKS and ERPNext; prints the env to use
```

## Container

```sh
docker build -t enterich:dev .                     # runtime image
docker build --target test -t enterich:test .      # runtime plus tests
docker run --rm enterich:test                      # runs the tests
```

The build installs from `uv.lock` with hashes, on amd64 and arm64 alike. The runtime image carries neither tests nor dev dependencies; the `test` stage adds both on top of it, so the tests run against the same packages.

## Rules for changes

- **Spec first.** A new operation, input or output field starts as a change to its area spec's catalogue ([specs index](../specs/README.md)), then tests, then code. Read REQ-001 too: its rules apply to every operation.
- **Tests first** for the token check and every operation: the e2e test asserts exactly what the fake ERPNext received.
- **The tool-list snapshot** changes only together with the area spec and a changelog line. Regenerate with `uv run pytest --snapshot-update` (syrupy) and review the diff; then write the README's tool list from it with `uv run python -m tests.readme`, which a test checks.
- **No deployment facts:** hostnames, realms, client names, user IDs, company names or credentials of a real site never go into code, tests or docs. Use `example.com`, `Example GmbH`, zero UUIDs.
- **Never log** keys, secrets or tokens; tests check it.
- **Changelog:** a line under `Unreleased` for every behaviour change, with **Rights** or **Configuration** headings where they apply ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).
- **Commits:** Conventional Commits (`feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`).
- **Scripts and CI** stay off `api.github.com`, which allows 60 requests an hour without a token; use `git ls-remote`, `raw.githubusercontent.com` or `releases.atom`. The exceptions are the release job's `gh release create` and CI's coverage comment (`gh pr comment`), both authenticated with the workflow's token: a release or a comment can't be created another way.

## CI

`ci.yml` runs on pull requests and pushes to `main`, without secrets: lock check, ruff, mdformat, the Markdown link check, basedpyright, pytest with branch coverage (the table in the run's summary and, for pull requests from this repository's branches, as one comment on the pull request that each push updates), a vulnerability audit of the lock, actionlint with shellcheck and zizmor (`scripts/check-workflows.sh`), gitleaks, and the image built for amd64 and arm64 with the tests run in its `test` stage. Nothing is published.

`release.yml` runs on a version tag, or by hand as a dry run, and builds through `image.yml`; the [releasing guide](releasing.md) describes both.

## References

- [Requirement specifications](../specs/README.md)
- [Architecture](../arc42/README.md)
- [Configuration](configuration.md)
