# ADR-004: SemVer tags, immutable, one multi-arch image per release

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |

## Context

Erpel is deployed by others from its image, and agents depend on its tool names and schemas. A deployment needs to know from a version number whether an update can change what the agent sees, what configuration it needs, or which ERPNext rights the agent user must have. Deployments update by hand, at a time they choose; a tag must mean one code state forever.

Deployments run on amd64; development machines may be arm64.

The repository is private until it moves to its organisation. Container packages on GHCR don't move with a repository, so nothing is published before the move.

## Decision

### Versions

- **SemVer `vX.Y.Z` Git tags**, annotated, created from `main`.
- **0.x until the tool list and configuration have settled.** While 0.x, a breaking change raises the minor version; from 1.0, the major.
- **What counts as the public interface:**
  - tool names, input schemas, output fields and annotations;
  - environment variables, their meaning and defaults;
  - HTTP paths, the metadata document and status codes;
  - the log's event names and fields;
  - the image's entrypoint, port and user;
  - the ERPNext rights the agent user needs.
- Removing or renaming any of these, tightening an input, or needing more ERPNext rights is breaking. A new tool, a new optional input or output field, a widened input limit or a new optional variable is a minor change. Fixes are patches.
- **A new tool is offered at once only where `ERPEL_TOOLS` is unset.** A deployment that lists its operations gets new ones only by adding them, so a minor update never widens what its agent can do.
- **Tags are immutable:** never moved, deleted or reused, enforced by a tag ruleset once the repository allows it.
- **One source for the version:** `version` in `pyproject.toml`; the release workflow refuses a tag that differs.
- **Security fixes for the latest minor version only,** released as a patch as soon as they are ready.

### Changelog

- `CHANGELOG.md` in Keep a Changelog format (Added, Changed, Deprecated, Removed, Fixed, Security). Every pull request that changes behaviour adds a line under `Unreleased`.
- Each release section has, besides Added/Changed/Fixed/Removed, a **Rights** heading when the agent user needs different ERPNext rights, and a **Configuration** heading when variables change.

### Image

- **`ghcr.io/interlusion/erpel:X.Y.Z`** (no `v`), published after the move only. No `latest`, no floating `X.Y` or `X` tags: deployments pin an exact version, preferably by digest.
- **Built once per tag** by CI from the tagged commit, for `linux/amd64` and `linux/arm64`, as one multi-arch index. A published version is never rebuilt; a fix is a new patch version.
- **Labels:** `org.opencontainers.image.version`, `.revision`, `.source`, `.licenses`.
- **Provenance and SBOM:** build provenance attestation and an SBOM, attached to the image, once the repository is public.
- **Pull requests and `main`** build and test the image for both architectures without pushing.
- **A dry run** of the release workflow, started by hand, does everything but publish; it runs before the first release and after every change to the workflow.

### What a release contains

- The Git tag and a GitHub release whose notes are the changelog section and the image digest.
- The image as above.
- The tool list in the README matching the tool-list snapshot of that commit.
- **The tool contract as a release asset:** `erpel-X.Y.Z-tools.json`, the tool-list snapshot of the tagged commit (every tool's name, description, input schema and annotations), which the release's tests have just matched against the running code. Deployments and reviewers diff it between versions to see what an update changes for the agent.

## Alternatives Considered

### Alternative 1: Upstream version plus build number (`<upstream version>-<build>`)

Common for images that package an upstream product.

**Rejected because**: Erpel has no upstream version to show; what a deployment needs to know is whether the interface changed.

### Alternative 2: Publish from every push to `main` with SHA tags

**Rejected because**: deployments update by hand and need versions they can read and a changelog per version.

### Alternative 3: Calendar versions

**Rejected because**: they say when, not whether an update is breaking.

### Alternative 4: A `latest` tag

**Rejected because**: it invites unpinned deployments of a service that holds an ERPNext key.

## Consequences

### Positive

- A deployment reads from the version and the changelog whether an update changes the agent's tools, the configuration or the rights.
- One tag, one image, one commit.

### Negative

- The interface is wide (tools, config, logs, rights), so 1.0 will take a while and 0.x releases may break often.
- A multi-arch build in CI takes longer than amd64 alone.

## Reconsideration Triggers

Revisit this decision when:

1. Deployments ask for automatic updates within a minor version.
2. The arm64 build becomes a burden and no one deploys on arm64.

## Compliance

- A tag SHALL NOT be moved, deleted or reused, and a published image tag SHALL NOT be overwritten.
- Images SHALL be pushed only by CI from a version tag, and not before the repository has moved to its organisation.
- A breaking change SHALL raise the major version (minor while 0.x) and SHALL be listed in the changelog.
- A change of the agent user's required ERPNext rights SHALL appear under **Rights** in the changelog.
- A new operation SHALL NOT be offered by an instance whose `ERPEL_TOOLS` doesn't name it.

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
- [OCI image annotations](https://github.com/opencontainers/image-spec/blob/main/annotations.md)
- [Releasing](../../guides/releasing.md)
