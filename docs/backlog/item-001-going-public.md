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
- [x] **History check:** search the whole Git history (all branches) for hostnames, realm and client names, user IDs, company names, keys and tokens of real deployments (`git log -p --all`, gitleaks over the history). If anything is found, rewrite or squash the history before the repository turns public, and have GitHub Support purge the old commits: pull request refs (`refs/pull/*`) keep them, and a rewrite doesn't remove those. Clean on 2026-10-29, covering every commit up to `2bee556`, all branches and the pull request refs.
- [ ] `SECURITY.md`: report vulnerabilities privately through GitHub's private vulnerability reporting; what's in scope (token check, tool limits, secret handling); supported versions (the latest minor version only); no bounty; response on a best-effort basis.
- [ ] README scope: maintained for our own use, contributions welcome, no support promised; status; link to the docs.
- [x] **Tool list in the README,** generated from the tool-list snapshot and checked against it in CI, so readers see every operation and the releasing guide's check has something to compare.
- [ ] **Product description (light spec):** a readable description of what Erpel does and doesn't do, derived from the specs, for the README, the website and user documentation. The specs stay authoritative; the light spec is updated whenever they change ([ADR-007](../arc42/adr/ADR-007-specs-by-accounting-area.md)).
- [ ] `CONTRIBUTING.md`: spec first, tests first, Conventional Commits, no deployment facts, how to run the tests.
- [ ] Issue and pull request templates; `CODEOWNERS`.
- [ ] **Logo:** SVG in a light and a dark variant (`docs/assets/`); a drake fits the name; nothing that uses or resembles ERPNext's or Frappe's marks ([ADR-006](../arc42/adr/ADR-006-licence-and-name.md)). The README header shows it, switching with the reader's colour scheme (`<picture>`). A 1280×640 PNG made from it for the social preview.
- [ ] **Version source:** the version in `pyproject.toml`, which the release workflow compares with the tag.
- [ ] **Release workflow** (`release.yml`) as the [releasing guide](../guides/releasing.md) describes it, including the dry run; the dry run passes on the default branch. It can't publish before the move, because it lacks the permissions.
- [ ] **Verifying an image:** a section in the [configuration guide](../guides/configuration.md) showing deployers how to check an image's provenance before deploying it (`gh attestation verify`), written against the final workflow.

The move:

- [ ] The history check repeated over the commits since `2bee556`.
- [ ] Transfer the repository to the organisation; confirm the redirect from the old name works for existing clones; update remotes.
- [ ] Make it public.

After the move:

- [ ] Organisation: two-factor authentication required for members; only owners may change repository visibility or create public packages; members' base permission read.
- [ ] Settings: private vulnerability reporting on; secret scanning and push protection on; Dependabot alerts and security updates on.
- [ ] Rulesets: `main` protected (pull request, green CI, no force push); tags `v*` immutable (no update, no deletion).
- [ ] Social preview image uploaded in the repository settings.
- [ ] `release.yml` given `packages: write`, `id-token: write` and `attestations: write`, for the tag-triggered job only; the dry run repeated in the organisation.
- [ ] Confirm the image name (`ghcr.io/interlusion/erpel`).
- [ ] First tag (`v0.1.0`) following the [releasing guide](../guides/releasing.md); the package linked to the repository and made public.
- [ ] Check the published image pulls on amd64 and arm64 and its attestation verifies (`gh attestation verify`).

After the first release:

- [ ] **MCP Registry:** a `server.json` in the repository describing Erpel and its image (reviewed and versioned like the code; updated by each release), published to the official MCP Registry. Check how third-party directories that copy the registry describe Erpel.
- [ ] **Announcement:** planned and done outside this repository; it follows the first release, never comes before it.

## Open Questions

- Should the organisation require signed commits or tags?
- OpenSSF Scorecard as a CI job after going public?
