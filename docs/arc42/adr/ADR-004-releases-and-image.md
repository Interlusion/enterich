# ADR-004: SemVer tags, immutable, one multi-arch image per release

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich is deployed by others from its image, and agents depend on its tool names and schemas. A deployment needs to know from a version number whether an update can change what the agent sees, what configuration it needs, or which ERPNext rights the agent user must have. Deployments update by hand, at a time they choose; a tag must mean one code state forever.

Deployments run on amd64; development machines may be arm64.

The repository moved to its organisation before the first release: container packages on GHCR don't move with a repository.

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
- **A new tool is offered at once only where `ENTERICH_TOOLS` is unset.** A deployment that lists its operations gets new ones only by adding them, so a minor update never widens what its agent can do.
- **Tags are immutable:** never moved, deleted or reused, enforced by a tag ruleset.
- **One source for the version:** `version` in `pyproject.toml`, set with `uv version`; the release workflow refuses a tag that differs.
- **Security fixes for the latest minor version only,** released as a patch as soon as they are ready.

### Changelog

- `CHANGELOG.md` in Keep a Changelog format (Added, Changed, Deprecated, Removed, Fixed, Security), written for deployers. Every pull request that changes behaviour adds a line under `Unreleased`.
- **Commits as the draft, not the text:** at release time, the `feat` and `fix` commits since the last tag (Conventional Commits) show what the section must cover; the section itself is written by hand.
- Each release section has, besides Added/Changed/Fixed/Removed, a **Rights** heading when the agent user needs different ERPNext rights, and a **Configuration** heading when variables change.

### Image

- **`ghcr.io/interlusion/enterich:X.Y.Z`** (no `v`). No `latest`, no floating `X.Y` or `X` tags: deployments pin an exact version, preferably by digest.
- **Built once per tag** by CI from the tagged commit, for `linux/amd64` and `linux/arm64`, as one multi-arch index. A published version is never rebuilt; a fix is a new patch version.
- **Labels:** `org.opencontainers.image.version`, `.revision`, `.source`, `.licenses`.
- **Provenance and SBOM:** build provenance attestation and an SBOM, attached to the image.
- **Pull requests and `main`** build and test the image for both architectures without pushing.
- **A dry run** of the release workflow, started by hand, does everything but publish; it runs before the first release and after every change the [releasing guide](../../guides/releasing.md#dry-run) names.

### What a release contains

- The Git tag and a GitHub release whose notes are the changelog section and the image digest.
- The image as above.
- The tool list in the README matching the tool-list snapshot of that commit.
- **The tool contract as a release asset:** `enterich-X.Y.Z-tools.json`, the tool-list snapshot of the tagged commit (every tool's name, description, input schema and annotations), which the release's tests have just matched against the running code. Deployments and reviewers diff it between versions to see what an update changes for the agent.

## Alternatives Considered

### Alternative 1: Upstream version plus build number (`<upstream version>-<build>`)

Common for images that package an upstream product.

**Rejected because**: Enterich has no upstream version to show; what a deployment needs to know is whether the interface changed.

### Alternative 2: Publish from every push to `main` with SHA tags

**Rejected because**: deployments update by hand and need versions they can read and a changelog per version.

### Alternative 3: Calendar versions

**Rejected because**: they say when, not whether an update is breaking.

### Alternative 4: A `latest` tag

**Rejected because**: it invites unpinned deployments of a service that holds an ERPNext key.

### Alternative 5: The version from the Git tag (`hatch-vcs`, `setuptools-scm`, `uv-dynamic-versioning`)

The build asks Git for the version: a tagged commit gets `X.Y.Z`, any other a development version naming the commit. Tag and code can't disagree, and a release needs no version edit.

**Rejected because**: its gain, telling untagged builds apart, doesn't apply: only CI publishes images, only from a tag. The mismatch it prevents is caught by the release workflow before anything is pushed. Its costs are concrete: `uv_build` can't take a version from Git, so another build backend; `.git` stays out of the image's build context, so the version must be passed in as a build argument, and an image built without it reports a wrong one; CI needs full clones wherever a version is built.

### Alternative 6: A changelog and version bump generated from commits (`git-cliff`, `release-please`, `python-semantic-release`)

Conventional Commits drive the changelog and the next version: `feat` raises the minor, `fix` the patch, `feat!` or a `BREAKING CHANGE` footer the major. Nothing is forgotten, and the release pull request writes itself.

**Rejected because**: the changelog is written for deployers, and commit subjects are written for developers. Its **Rights** and **Configuration** headings have no commit type. One change usually spans several commits (`docs`, `test`, `feat`), so entries would follow commits, not changes. And the version would be only as right as each commit's marking: a tightened input or a new required right committed as a plain `feat` would ship as a minor change after 1.0. The commits still serve as the draft (see Changelog).

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
- Images SHALL be pushed only by CI from a version tag.
- A breaking change SHALL raise the major version (minor while 0.x) and SHALL be listed in the changelog.
- A change of the agent user's required ERPNext rights SHALL appear under **Rights** in the changelog.
- A new operation SHALL NOT be offered by an instance whose `ENTERICH_TOOLS` doesn't name it.

## References

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
- [OCI image annotations](https://github.com/opencontainers/image-spec/blob/main/annotations.md)
- [Releasing](../../guides/releasing.md)
