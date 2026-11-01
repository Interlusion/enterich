# ITEM-003: MCP Registry and announcement

| Meta | Value |
| :- | :- |
| **Status** | IN PROGRESS |
| **Type** | feature |
| **Origin** | [ITEM-001](archive/item-001-going-public.md)'s steps after the first release, moved here on 2026-10-30 |
| **Created** | 2026-10-30 |
| **Author** | loxy (drafted with Claude) |

## Summary

List Enterich in the official MCP Registry, published by each release, and announce it once the listing and a test against a real ERPNext are done.

## Context / Motivation

The registry makes Enterich findable for MCP clients and for the directories that copy the registry. It accepts container images from GHCR (registry documentation as of 2026-10-30):

- **Ownership:** the image carries the label `io.modelcontextprotocol.server.name`, equal to the `name` in `server.json`. The v0.1.0 image doesn't, and a published image never changes, so the listing starts with the next release.
- **Namespace:** `io.github.interlusion/…` needs GitHub OIDC from a workflow, or a personal token that can read the organisation's members; the interactive GitHub login can't publish for an organisation. A domain namespace (`de.interlusion/…`) needs a DNS TXT record and a key, and stays valid wherever the code lives.
- **Format:** an OCI package with `streamable-http` transport and a URL template for the port, and the `ENTERICH_` variables as environment variables, the secrets marked as such.

Enterich isn't a typical entry: it is a service behind an authorization server, not a tool a client starts for itself. A client that installs from the registry would start the image locally, which isn't how Enterich runs; the listing is for finding it, and its description says so.

The announcement follows the listing and the test against a real ERPNext ([ITEM-004](archive/item-004-real-erpnext-test.md)), so that what it points to has been tried on a real site.

## To do

- [x] Decide the namespace and how the entry is published (below).
- [x] The label in the `Dockerfile`'s runtime stage, checked by the dry run's `scripts/image_index.py`.
- [x] `server.json` in the repository: name, description, repository, version, the OCI package with its transport and variables; reviewed and versioned like the code, its version set with each release. A repository check holds it to the image's label, `pyproject.toml`'s version and the configuration guide's variables; the dry run validates it with `mcp-publisher`.
- [x] Publishing in the release workflow's tag run, after the image is pushed: the `registry` job, with the key of the environment `mcp-registry`.
- [ ] The key and the DNS record, set up by the operator (releasing guide, "The MCP Registry key").
- [ ] The release that carries it; then check the entry, and how third-party directories that copy the registry describe Enterich.
- [ ] **Announcement:** planned and done outside this repository, after the entry and the real-ERPNext test.

## Open Questions

None. Decided on 2026-11-01:

- **Namespace** `dev.interlusion/enterich`, proven by a TXT record on `interlusion.dev`, Interlusion's website domain (`interlusion.de` redirects to it). A domain names the publisher rather than where the code lives, and stays valid if the repository moves; the price is a private key kept as a secret, where `io.github.interlusion` with OIDC would need none.
- **Published by the release workflow's tag run**, in a job of its own that alone reads the key from a protected environment.

## Notes

- Registry documentation: [package types](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/package-types.mdx), [authentication](https://github.com/modelcontextprotocol/registry/blob/main/docs/modelcontextprotocol-io/authentication.mdx), [server.json](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/server-json/generic-server-json.md).
