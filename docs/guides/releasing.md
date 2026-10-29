# Releasing

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: no release before the repository has moved ([ITEM-001](../backlog/item-001-going-public.md)) |

Why it works this way: [ADR-004](../arc42/adr/ADR-004-releases-and-image.md).

## Choose the version

Compare `CHANGELOG.md`'s `Unreleased` section with the last release:

| Change | 0.x | from 1.0 |
| :- | :- | :- |
| Tool, input, output field, variable, path, log field or image interface removed, renamed or tightened; more ERPNext rights needed | minor | major |
| New tool, optional input or output field, widened input limit, optional variable | minor | minor |
| Fix without interface change | patch | patch |

## The version

The version lives in one place: `version` in `pyproject.toml`. Erpel reports it at start (`start` log event), and the release workflow refuses a tag that doesn't equal it.

## Steps

1. **On a branch:** set `version` in `pyproject.toml` to `X.Y.Z`, move `Unreleased` to `## [X.Y.Z] - YYYY-MM-DD` in `CHANGELOG.md`, and add the compare link; the README's tool list is checked against `tests/snapshots/tools.json` by the tests. Open a pull request (`chore: release vX.Y.Z`); merge when CI is green.
2. **Tag the merge commit on `main`:**
   ```sh
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "Erpel vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. **CI** (`release.yml`, triggered by the tag) checks that the tag equals the version in `pyproject.toml`, builds the image for amd64 and arm64 once, runs the tests in its `test` stage, pushes the runtime image `ghcr.io/interlusion/erpel:X.Y.Z`, attaches provenance and SBOM, and creates the GitHub release with the changelog section and the digest, and attaches `tests/snapshots/tools.json` as `erpel-X.Y.Z-tools.json`.
4. **Check** the release page: notes, digest, both architectures, the tools asset.

## Dry run

`release.yml` can also be started by hand (`workflow_dispatch`) with a version. It then does everything up to publishing (version check, build for both architectures, tests, SBOM, release notes and tools file as workflow artefacts) and pushes, tags and releases nothing. Run it before the first release and after every change to `release.yml`: a published image tag can never be reused, so a broken first publish can't be retried under the same version.

## When it fails

A release workflow that failed for a passing reason (a registry or runner outage) is re-run for the same tag, if nothing was pushed. Anything that needs a commit, including a fix to `release.yml`, needs a new patch version: the tag can't move to the fixed commit.

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
