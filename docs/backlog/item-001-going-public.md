# ITEM-001: Going public

| Meta | Value |
| :- | :- |
| **Status** | CANDIDATE |
| **Type** | feature |
| **Origin** | [ADR-004](../arc42/adr/ADR-004-releases-and-image.md); project rules in `AGENTS.md` |
| **Created** | 2026-10-23 |
| **Author** | loxy (drafted with Claude) |

## Summary

Move the repository to its organisation, make it public, and publish the first release with its image. Until then, no tags and no images.

## Checklist

Before the move:

- [x] REQ-001 to REQ-007 and ADR-001 to ADR-007 accepted; the operations of the specs built and tested.
- [x] **History check:** search the whole Git history (all branches) for hostnames, realm and client names, user IDs, company names, keys and tokens of real deployments (`git log -p --all`, gitleaks over the history). If anything is found, rewrite the history before the first push to the organisation's repository; only `main` goes there, so the old repository's pull request refs don't come along. Clean on 2026-10-29, covering every commit up to `2bee556` and all branches.
- [x] `SECURITY.md`: report vulnerabilities privately through GitHub's private vulnerability reporting; what's in scope (token check, tool limits, secret handling); supported versions (the latest minor version only); no bounty; response on a best-effort basis.
- [x] README scope: maintained for our own use, contributions welcome, no support promised; status; link to the docs.
- [x] **Tool list in the README,** generated from the tool-list snapshot and checked against it in CI, so readers see every operation and the releasing guide's check has something to compare.
- [x] **No separate product description (light spec):** decided against. The README says what Enterich is and isn't, and its generated tool list names each area's scope from the specs index; the guides cover operators and reviewers; the specs hold the details. A prose copy of the specs would drift with no test to catch it, and a website writes its copy from these when it needs one.
- [x] `CONTRIBUTING.md`: spec first, tests first, Conventional Commits, no deployment facts, how to run the tests.
- [x] Issue and pull request templates; `CODEOWNERS`.
- [ ] **Logo:** SVG in a light and a dark variant (`docs/assets/`); a drake fits the name; nothing that uses or resembles ERPNext's or Frappe's marks ([ADR-006](../arc42/adr/ADR-006-licence-and-name.md)). The README header shows it, switching with the reader's colour scheme (`<picture>`). A 1280×640 PNG made from it for the social preview.
- [x] **Version source:** the version in `pyproject.toml`, which the release workflow compares with the tag.
- [x] **Release workflow** (`release.yml`) as the [releasing guide](../guides/releasing.md) describes it, including the dry run; the dry run passes on the default branch. It can't publish before the move: it lacks the permissions, and refuses a tag outside `interlusion/enterich`. The dry run passed on `main` on 2026-10-29; it is repeated after every change to the workflows, as the releasing guide says.
- [x] **The repository named `enterich`:** created empty and private as `Interlusion/enterich`, so the code moves by a push, not a transfer.
- [x] **Verifying an image:** a section in the [configuration guide](../guides/configuration.md) showing deployers how to check an image's provenance before deploying it (`gh attestation verify`), written against the final workflow.

The move:

- [ ] The history check repeated over `main` since `2bee556`.
- [ ] Push `main` to `Interlusion/enterich`, still private, and point the remotes there. Issues, pull requests and their refs stay behind in the old repository, and there is no redirect; tags follow with the first release.
- [ ] CI and the release dry run pass in `Interlusion/enterich`; the dry run also covers the workflows as the rename changed them (image name, asset names, repository guard).
- [ ] Make it public, and in the same step switch on private vulnerability reporting (`SECURITY.md`'s only channel, which GitHub offers for public repositories), secret scanning and push protection.
- [ ] Archive the old repository.

After the move:

- [ ] Organisation: two-factor authentication required for members; only owners may change repository visibility or create public packages; members' base permission read.
- [ ] Settings: Dependabot alerts and security updates on.
- [ ] Rulesets: `main` protected (pull request, green CI, no force push); tags `v*` immutable (no update, no deletion).
- [ ] Social preview image uploaded in the repository settings.
- [ ] `release.yml`'s `publish` job given `packages: write`, `id-token: write`, `attestations: write`, `artifact-metadata: write` (the attestation's storage record, which the action creates in an organisation) and `contents: write` (for the GitHub release), that job only; the dry run repeated in the organisation.
- [ ] Confirm the image name (`ghcr.io/interlusion/enterich`).
- [ ] `CODEOWNERS` names an organisation team instead of `@loxy`.
- [ ] First tag (`v0.1.0`) following the [releasing guide](../guides/releasing.md); the package linked to the repository and made public.
- [ ] Check the published image pulls on amd64 and arm64 and its attestation verifies (`gh attestation verify`).

After the first release:

- [ ] **MCP Registry:** a `server.json` in the repository describing Enterich and its image (reviewed and versioned like the code; updated by each release), published to the official MCP Registry. Check how third-party directories that copy the registry describe Enterich.
- [ ] **Announcement:** planned and done outside this repository; it follows the first release, never comes before it.

## Open Questions

- Should the organisation require signed commits or tags?
- OpenSSF Scorecard as a CI job after going public?
