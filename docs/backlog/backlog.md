# Backlog

Quick items. Items with detail have their own file (`item-NNN-*.md`); done or rejected ones move to `archive/`.

- [ ] Licence check of the locked dependencies in CI (no copyleft in the image).
- [ ] Release candidates (`vX.Y.Z-rc.N`) published as GitHub pre-releases, to rehearse a whole release, including GHCR sign-in, push, attestation and the GitHub release, which the dry run can't run: v0.2.0's `registry` job failed on such a step, a called workflow without its environment's secret. Needs ADR-004 and the release workflow's version check to allow pre-release versions, and leaves the candidates' images public. Not for the first release (decided 2026-10-30); reconsider after it.
- [ ] Signed commits or tags: should the organisation require them?
- [ ] OpenSSF Scorecard as a CI job, now that the repository is public.
- [ ] When the organisation gets a second member: members' base permission read; only owners may change repository visibility or create public packages; `CODEOWNERS` names an organisation team instead of `@loxy`, with write access to the repository.
- [ ] Drafts of returns (credit notes) against submitted invoices.
- [ ] Payment entry drafts.
- [ ] Several agent identities in one instance, each with its own ERPNext key (ADR-003 trigger 3).
- [ ] Keycloak guide: a second setup for agents that run on their own, with the client credentials grant (a confidential client with a service account, no browser sign-in). No person's session can then get a token through the agent's client, and no refresh tokens are issued; the client secret is the only factor. Enterich needs no change (ADR-003). First check which MCP clients can use it, and try it with Enterich.
- [ ] `_FILE` variants of the secret variables, for secrets mounted as files.
- [ ] Optional check of the sign-in method (`acr`) for deployments that need Enterich to require a second factor itself (ADR-003 trigger 4).
- [ ] Optional maximum access-token lifetime (`exp` − `iat`), if deployments can't keep tokens short at the authorization server.
