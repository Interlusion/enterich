# Development

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: everything below is built except, in `tools/`, the areas after procure to pay, and `python -m tests.fakes` (the fakes run in tests only) |

## Repository layout

```
src/erpel/
  __main__.py        entry point: python -m erpel
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
  e2e/               Erpel against a fake JWKS and a fake ERPNext, named
                     by area like tools/, an area's drafts in their own
                     module (test_order_to_cash_drafts.py)
  fakes/             the fakes, recording every request
  snapshots/         tools.json: the published tool list
docs/                specs, architecture, ADRs, guides, backlog
AGENTS.md            rules for coding agents; CLAUDE.md imports it
Dockerfile           build, runtime and test stages
pyproject.toml, uv.lock, .python-version
.github/workflows/   ci.yml (later: release.yml)
.github/dependabot.yml
```

Why this toolchain: [ADR-005](../arc42/adr/ADR-005-toolchain-and-dependencies.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/). uv installs the Python version named in `.python-version`.

```sh
uv sync --locked           # creates .venv from uv.lock, with dev tools
uv run pytest              # all tests, no network, no ERPNext needed
uv run ruff check && uv run ruff format --check
uv run mdformat --check .  # Markdown; without --check it formats
uv run basedpyright
uv run erpel               # starts Erpel; needs the ERPEL_* variables
```

Run Erpel locally against the fakes:

```sh
uv run python -m tests.fakes   # fake JWKS and ERPNext; prints the env to use
```

## Container

```sh
docker build -t erpel:dev .                     # runtime image
docker build --target test -t erpel:test .      # runtime plus tests
docker run --rm erpel:test                      # runs the tests
```

The build installs from `uv.lock` with hashes, on amd64 and arm64 alike. The runtime image carries neither tests nor dev dependencies; the `test` stage adds both on top of it, so the tests run against the same packages.

## Rules for changes

- **Spec first.** A new operation, input or output field starts as a change to its area spec's catalogue ([specs index](../specs/README.md)), then tests, then code. Read REQ-001 too: its rules apply to every operation.
- **Tests first** for the token check and every operation: the e2e test asserts exactly what the fake ERPNext received.
- **The tool-list snapshot** changes only together with the area spec and a changelog line. Regenerate with `uv run pytest --snapshot-update` (syrupy) and review the diff.
- **No deployment facts:** hostnames, realms, client names, user IDs, company names or credentials of a real site never go into code, tests or docs. Use `example.com`, `Example GmbH`, zero UUIDs.
- **Never log** keys, secrets or tokens; tests check it.
- **Changelog:** a line under `Unreleased` for every behaviour change, with **Rights** or **Configuration** headings where they apply ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).
- **Commits:** Conventional Commits (`feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`).
- **Scripts and CI** stay off `api.github.com`; use `git ls-remote`, `raw.githubusercontent.com` or `releases.atom`.

## CI

`ci.yml` runs on pull requests and pushes to `main`, without secrets: lock check, ruff, mdformat, basedpyright, pytest with coverage, a vulnerability audit of the lock, actionlint, zizmor, gitleaks, and the image built for amd64 and arm64 with the tests run in its `test` stage. Nothing is published.

## References

- [Requirement specifications](../specs/README.md)
- [Architecture](../arc42/README.md)
- [Configuration](configuration.md)
