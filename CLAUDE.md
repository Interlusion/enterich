# CLAUDE.md

## Project

erpel: an MCP server for ERPNext with a fixed tool list, tokens from an
external OAuth authorization server, and only the rights of one ERPNext
agent user. See `README.md`.

The repository is private under `loxy` for now and moves to the Interlusion
organisation before it goes public. Write everything as if it were public
already.

## Rules

- **Nothing specific to one deployment goes into this repository**: no
  hostnames, realm or client names, user IDs, credentials, or a site's tool
  selection. Configuration comes from environment variables; examples use
  placeholders such as `erp.example.com`.
- **Secrets never in Git**, and never in logs: API keys, secrets, access and
  refresh tokens.
- **Tools have a fixed purpose and input schema.** No tool takes a DocType,
  method name, field list or file path as input.
- **No limit may depend on the MCP client asking for approval.**
- The names "ERPNext" and "Frappe" don't go into the project or package
  name (Frappe's trademark policy); descriptions may say "for ERPNext".
- Don't publish container images until the repository has moved to the
  Interlusion organisation (GHCR packages don't move with a repository).

## Conventions

- Conventional Commits: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`,
  `test`.
- Keep scripts and agents off `api.github.com` (60 requests/h
  unauthenticated): use `git ls-remote`, `raw.githubusercontent.com`,
  `releases.atom`.
- Commit or push only when the operator asks.
