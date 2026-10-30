# Development

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: matches what is built |

## Repository layout

The package's modules and what each is responsible for: [architecture, section 5](../arc42/README.md#5-building-block-view).

```
src/enterich/        the package; __main__.py is the entry point (python -m enterich)
tests/
  unit/              per module
  integration/       Enterich against a fake JWKS and a fake ERPNext, named
                     by area like tools/, an area's drafts in their own
                     module (test_order_to_cash_drafts.py)
  repo/              checks of repository files (README, changelog, guides,
                     scripts); not in the image, which runs unit/ and integration/
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

The tests have three levels:

- **Unit:** one module, its collaborators replaced where they reach outside.
- **Integration:** Enterich as a whole, from the MCP request to its ERPNext calls, with its neighbours faked: the authorization server's keys (`FakeJwks`) and ERPNext (`FakeErpnext`).
- **End-to-end:** from the MCP request to a real ERPNext site; only the token issuer is faked. Not built yet.

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

## Container

```sh
docker build -t enterich:dev .                     # runtime image
docker build --target test -t enterich:test .      # runtime plus tests
docker run --rm enterich:test                      # runs the tests
```

The build installs from `uv.lock` with hashes, on amd64 and arm64 alike. The runtime image carries neither tests nor dev dependencies; the `test` stage adds both on top of it, so the tests run against the same packages.

## Rules for changes

- **Spec first.** A new operation, input or output field starts as a change to its area spec's catalogue ([specs index](../specs/README.md)), then tests, then code. Read REQ-001 too: its rules apply to every operation.
- **Tests first** where a spec's Definition of Done describes the behaviour: the failing test is written from it, run red and committed before the code (`test:`, then `feat:` or `fix:`). Infrastructure (image, CI) and trying out a library's behaviour are exceptions; what they teach becomes a test afterwards. An operation's integration test asserts exactly what the fake ERPNext received.
- **The tool-list snapshot** changes only together with the area spec and a changelog line. Regenerate with `uv run pytest --snapshot-update` (syrupy) and review the diff; then write the README's tool list from it with `uv run python -m tests.readme`, which a test checks.
- **No deployment facts:** hostnames, realms, client names, user IDs, company names, credentials or a site's tool selection never go into code, tests, docs or commit messages. Use `example.com`, `Example GmbH`, zero UUIDs.
- **Never log** keys, secrets or tokens; tests check it.
- **Changelog:** a line under `Unreleased` for every behaviour change, with **Rights** or **Configuration** headings where they apply ([ADR-004](../arc42/adr/ADR-004-releases-and-image.md)).
- **Commits:** Conventional Commits (`feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`).
- **Scripts and CI** stay off `api.github.com`, which allows 60 requests an hour without a token; use `git ls-remote`, `raw.githubusercontent.com` or `releases.atom`. The exceptions are the release job's `gh release create` and CI's coverage comment (`gh pr comment`), both authenticated with the workflow's token: a release or a comment can't be created another way.

## CI

`ci.yml` runs on pull requests and pushes to `main`, without secrets: the lock, ruff, mdformat, the Markdown link check, basedpyright, pytest with branch coverage (the table in the run's summary and, for pull requests from this repository's branches, as one comment on the pull request that each push updates), a vulnerability audit of the lock, actionlint with shellcheck and zizmor (`scripts/check-workflows.sh`), gitleaks, and the image built for amd64 and arm64, each on a runner of its own architecture, with the tests run in its `test` stage. Nothing is published.

`release.yml` runs on a version tag, or by hand as a dry run, and builds through `image.yml`; the [releasing guide](releasing.md) describes both.

## References

- [Requirement specifications](../specs/README.md)
- [Architecture](../arc42/README.md)
- [Configuration](configuration.md)
