# ADR-005: Python with uv: lock with hashes, Dependabot, pinned base image and Actions

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich holds an ERPNext API key and sits on the internet. Every dependency runs with that key in reach, so what goes into the image must be exactly what was reviewed and tested. The spike pinned every dependency with a hash, but only for amd64 wheels, which broke installs on arm64 development machines.

The MCP SDK changes how Enterich talks to clients; an SDK update needs more care than a patch of a utility library.

## Decision

### Toolchain

- **One Python version.** Enterich is an application, not a library, so it runs on exactly one version. A new Python version is adopted once it has been released for a year and every dependency supports it; until then the previous one stays. `.python-version`, `requires-python` (`==3.N.*`) and the base image name the same version and change together in one pull request.
- **uv** for the project: `pyproject.toml` declares the direct dependencies, `uv.lock` pins every package with hashes for all platforms. `uv_build` is the build backend; development tools are a dependency group (PEP 735), not an optional extra; `enterich` is a console script; the version is read at runtime from the package metadata.
- **ruff** for linting and formatting Python; **mdformat** with `mdformat-gfm` for Markdown, configured in `.mdformat.toml` (one line per paragraph, consecutive list numbers, tables without padding, so a change shows as one changed line); **basedpyright** in strict mode for types (it installs Node.js as a locked Python package, where `pyright` downloads it on first run); **pytest** with anyio's plugin for async tests (anyio already comes with the SDK), **coverage** with branch coverage, **syrupy** for the tool-list snapshot.
- **Configuration with plain pydantic models**, no `pydantic-settings`; **logging with the standard library** and a small JSON formatter.
- **HTTP client: `httpx2`,** the one the MCP SDK already depends on, so the image carries one HTTP stack; created with `trust_env=False`, so no proxy or certificate setting from the environment reaches the ERPNext calls.
- **Layout:** `src/enterich/` (package), `tests/` (unit and integration tests with a fake ERPNext and a fake JWKS), `Dockerfile`, `.github/`.

### Pins

- **The MCP SDK pinned exactly** (`mcp==X.Y.Z`) in `pyproject.toml`; other direct dependencies with lower bounds; the lock pins all.
- **The image installs from the lock only,** following uv's Docker guide:
  - the build stage uses the uv binary from its pinned image and the same Python base image as the runtime stage, with uv's own Python downloads off (`UV_PYTHON_DOWNLOADS=0`), so the copied virtual environment finds its interpreter at the same path;
  - `uv sync --locked --no-dev --no-install-project` first (a layer that only changes with the lock), then `uv sync --locked --no-dev --no-editable` with the code; `--locked` fails on a stale lock, and uv checks the lock's hashes;
  - bytecode compiled at build time (`UV_COMPILE_BYTECODE=1`);
  - the runtime stage copies the virtual environment, nothing else, and sets `PYTHONUNBUFFERED=1`. No resolution at build time.
- **A `test` stage** on top of the runtime stage adds the dev dependencies (also from the lock) and the tests. CI runs the tests in it; the runtime image, which is what gets published, carries neither.
- **Base images pinned by digest** (the Python `slim` image and the uv image, each as `name:tag@sha256:…`). The runtime image runs as a numeric non-root user, so Kubernetes' `runAsNonRoot` works, and writes nothing at runtime, so a read-only root filesystem works.
- **GitHub Actions pinned by commit SHA**, with the version as a comment.

### Updates

- **Dependabot** for `uv`, `docker` and `github-actions`, weekly, minor and patch updates grouped per ecosystem.
- **The MCP SDK is never grouped:** its own pull request, read against the SDK's changelog, and before a release tested against a real client.
- **Dependabot security updates** on; a security fix is released as a patch.

### CI

On every pull request and push to `main`, without secrets:

- `uv sync --locked`, which also fails when the lock doesn't match `pyproject.toml`;
- ruff (check and format), mdformat (`--check`), the Markdown link check, basedpyright;
- pytest, including the token cases and the tool-list snapshot, with branch coverage reported (not a gate) in the run's summary and, for pull requests from this repository's branches, as a comment;
- a vulnerability audit of the locked dependencies with `uv audit` (OSV), so a known vulnerability stops a pull request before Dependabot's alert after the merge;
- actionlint, with shellcheck for their `run:` scripts, and zizmor for the workflows;
- gitleaks over the diff;
- the image built for `linux/amd64` and `linux/arm64`, each on a runner of its own architecture, with the tests run in its `test` stage.

Workflows get `contents: read`. A job that needs more gets it alone and runs no code from the pull request: the coverage comment (`pull-requests: write`), and the release's publish job (releasing guide).

## Alternatives Considered

### Alternative 1: pip-tools with `requirements.txt` and hashes

**Rejected because**: `pip-compile --generate-hashes` resolves for the platform it runs on; covering amd64 and arm64 needs two files or manual merges.

### Alternative 2: Poetry

**Rejected because**: slower, and its lock is not consumed as directly by an image build with hash checks.

### Alternative 3: Renovate

**Rejected because**: an external app with broad repository access where Dependabot covers the three ecosystems.

### Alternative 4: mypy

**Rejected because**: pyright (here as basedpyright) is faster and stricter for pydantic models; either would do.

### Alternative 5: Always the newest Python

**Rejected because**: compiled dependencies and the base images lag behind a new release, and its early patch releases fix the most.

### Alternative 6: Staying on a Python version until its end of life

**Rejected because**: it leaves less support time when a forced upgrade comes, and turns several small upgrades into one large one.

### Alternative 7: pytest-asyncio

**Rejected because**: the SDK is built on anyio, whose pytest plugin comes with it; a second async test plugin adds a dependency for nothing.

### Alternative 8: Prettier for Markdown

**Rejected because**: it runs on Node, so contributors and CI would need npm next to uv; mdformat installs from the same lock, with hashes.

### Alternative 9: actionlint and shellcheck from PyPI (`actionlint-py`, `shellcheck-py`)

actionlint checks the workflows' `run:` scripts with shellcheck only where shellcheck is installed; from PyPI, both would come from the lock like the other tools.

**Rejected because**: `shellcheck-py` has no Linux arm64 wheel, and built from source it downloads the shellcheck binary without a hash check. actionlint's own image brings shellcheck instead, pinned by digest like the other images CI runs.

## Consequences

### Positive

- The same lock drives development on arm64, CI and the image on both architectures.
- Every change to what runs in the image is a reviewed pull request.

### Negative

- Weekly Dependabot pull requests to review.
- uv is a further tool for contributors (one binary).

## Reconsideration Triggers

Revisit this decision when:

1. Python changes its release or support cycle.
2. Dependabot's uv support falls behind uv's lock format.

## Compliance

- The image SHALL install only packages from `uv.lock`, with hashes checked.
- The MCP SDK SHALL be pinned to one exact version.
- Base images SHALL be pinned by digest, Actions by commit SHA.
- CI SHALL NOT have access to secrets on pull requests.

## References

- [uv: locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [Dependabot supported ecosystems](https://docs.github.com/en/code-security/dependabot/ecosystems-supported-by-dependabot/supported-ecosystems-and-repositories)
- [ADR-002](ADR-002-mcp-sdk-stateless-streamable-http.md), [ADR-004](ADR-004-releases-and-image.md)
- [Development](../../guides/development.md)
