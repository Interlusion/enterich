# Backlog

Quick items. Items with detail have their own file (`item-NNN-*.md`); done or rejected ones move to `archive/`.

- [ ] Integration test against a real ERPNext v16 container (seeded company, agent user with the minimum role), run on demand or nightly, not on every pull request. Besides each operation, it shows that the agent user's key is refused for submit (`frappe.client.submit` and a save with `docstatus` 1), cancel, delete, amend and discard; that report filters and columns match the catalogue; that the duplicate check finds drafts made by people; and that select-only rights lose fields.
- [ ] Licence check of the locked dependencies in CI (no copyleft in the image).
- [ ] Native arm64 runner for the release build in `image.yml`, as `ci.yml` has it: the arm64 test stage and image built on `ubuntu-24.04-arm` instead of with QEMU. The multi-arch index is built in one job today, so this means one build per architecture pushed by digest, a job that joins them into the index, and the SBOM, provenance, attestation and the dry run's index check moved along; the dry run shows the result.
- [ ] Release candidates (`vX.Y.Z-rc.N`) published as GitHub pre-releases, to rehearse a whole release, including GHCR sign-in, push, attestation and the GitHub release, which the dry run can't run. Needs ADR-004 and the release workflow's version check to allow pre-release versions, and leaves the candidates' images public. Decide before the first release after the move ([ITEM-001](item-001-going-public.md)).
- [ ] Drafts of returns (credit notes) against submitted invoices.
- [ ] Payment entry drafts.
- [ ] Several agent identities in one instance, each with its own ERPNext key (ADR-003 trigger 3).
- [ ] Keycloak guide: a second setup for agents that run on their own, with the client credentials grant (a confidential client with a service account, no browser sign-in). No person's session can then get a token through the agent's client, and no refresh tokens are issued; the client secret is the only factor. Enterich needs no change (ADR-003). First check which MCP clients can use it, and try it with Enterich.
- [ ] `_FILE` variants of the secret variables, for secrets mounted as files.
- [ ] Optional check of the sign-in method (`acr`) for deployments that need Enterich to require a second factor itself (ADR-003 trigger 4).
- [ ] Optional maximum access-token lifetime (`exp` − `iat`), if deployments can't keep tokens short at the authorization server.
