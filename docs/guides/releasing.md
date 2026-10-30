# Releasing

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: no release yet; the first follows [ITEM-001](../backlog/item-001-going-public.md) |

Why it works this way: [ADR-004](../arc42/adr/ADR-004-releases-and-image.md).

## Choose the version

Compare `CHANGELOG.md`'s `Unreleased` section with the last release:

| Change | 0.x | from 1.0 |
| :- | :- | :- |
| Tool, input, output field, variable, path, log field or image interface removed, renamed or tightened; more ERPNext rights needed | minor | major |
| New tool, optional input or output field, widened input limit, optional variable | minor | minor |
| Fix without interface change | patch | patch |

## The version

The version lives in one place: `version` in `pyproject.toml`, set with `uv version X.Y.Z` and shown with `uv version --short`. Enterich reports it at start (`start` log event), and the release workflow refuses a tag that doesn't equal it.

## Steps

1. **On a branch:** run `uv version X.Y.Z`; check the `Unreleased` section against the `feat` and `fix` commits since the last tag (`git log --oneline vLAST.. | grep -E '^[0-9a-f]+ (feat|fix)'`), then move it to `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md` and add the compare link; the README's tool list is checked against `tests/snapshots/tools.json` by the tests. Open a pull request (`chore: release vX.Y.Z`); merge when CI is green.
2. **Tag the merge commit on `main`:**
   ```sh
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "Enterich vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. **CI** (`release.yml`, triggered by the tag) checks that the tag equals the version in `pyproject.toml`, is annotated, is on `main` and was pushed to `interlusion/enterich`, and that `CHANGELOG.md` has the version's section. Then `image.yml` builds the `test` stage for amd64 and arm64, each on a runner of its own architecture, and runs the tests in it; builds the runtime image for both once, from the layers the tests ran on; pushes the runtime image `ghcr.io/interlusion/enterich:X.Y.Z` with its SBOM and provenance, adds a build provenance attestation, and creates the GitHub release with the changelog section and the digest, attaching `tests/snapshots/tools.json` as `enterich-X.Y.Z-tools.json`.
4. **Check** the release page: notes, digest, both architectures, the tools asset.

## Dry run

`release.yml` can also be started by hand (`workflow_dispatch`) with a version: in GitHub under Actions, Release, Run workflow, or `gh workflow run release.yml -f version=X.Y.Z`. It runs the same `image.yml` as a release, with read rights only: the version check, the build for both architectures, the tests in both, and the same build step for the runtime image, which it writes as an OCI image layout instead of pushing it. `scripts/image_index.py` then checks that the layout holds the image under its release name for both architectures, each with SBOM and provenance, and that no provenance carries GitHub's event payload, which for a tag push names people with their email addresses. The run's artefact `dry-run-X.Y.Z` holds the release notes, the tools file, and the SBOM and provenance per architecture. The version must equal `pyproject.toml`'s, so a dry run checks the version about to be released; where `CHANGELOG.md` has no section for it yet, as before the first release, the notes are the `Unreleased` section.

Only a tag run signs in to GHCR, pushes, attests and creates the release; those steps are first run for real. Run the dry run before the first release and after every change to `release.yml`, `image.yml`, the scripts they run or the `Dockerfile`.

## When it fails

A release run that failed for a passing reason (a registry or runner outage) is re-run with **Re-run failed jobs**:

- If a `test` job or the `image` job failed, nothing was pushed, and they run again. The `image` job refuses to start when the version's image exists already, so a published image tag is never overwritten. It takes the layers from the `test` jobs' build caches, which are kept for 7 days; after that, re-run all jobs.
- If the `release` job failed (attestation or GitHub release), only it runs again, for the image already pushed.

Anything that needs a commit, including a fix to the workflows, needs a new patch version: the tag can't move to the fixed commit.

## Security fixes

- Only the latest minor version gets fixes. A deployment on an older one updates to the latest; the changelog says what that changes.
- A security fix is released as soon as it is ready, as a patch of the latest minor version, with a **Security** heading in the changelog. A vulnerability reported privately gets a GitHub security advisory, published with the release.
- Dependabot security updates follow the same path: merge, then a patch release.

## Never

- Move, delete or reuse a tag; overwrite an image tag; push an image by hand.
- Publish `latest` or floating tags.

## References

- [ADR-004](../arc42/adr/ADR-004-releases-and-image.md)
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
