# AGENTS.md

Instructions for coding agents working on Erpel. `CLAUDE.md` imports this file; edit the rules here.

## Project

Erpel: an MCP server for ERPNext with a fixed tool list, tokens from an external OAuth authorization server, and only the rights of one ERPNext agent user. See `README.md`.

The repository is private under `loxy` for now and moves to the Interlusion organisation before it goes public. Write everything as if it were public already.

## Rules

- **Nothing specific to one deployment goes into this repository**: no hostnames, realm or client names, user IDs, credentials, or a site's tool selection. Configuration comes from environment variables; examples use placeholders such as `erp.example.com`.
- **Secrets never in Git**, and never in logs: API keys, secrets, access and refresh tokens.
- **Tools have a fixed purpose and input schema.** No tool takes a DocType, method name, field list or file path as input.
- **No limit may depend on the MCP client asking for approval.**
- The project is **Erpel** in prose, `erpel` as an identifier (package, command, repository, image), `ERPEL_` for variables.
- The names "ERPNext" and "Frappe" don't go into the project or package name (Frappe's trademark policy); descriptions may say "for ERPNext".
- Don't publish container images until the repository has moved to the Interlusion organisation (GHCR packages don't move with a repository).

## Docs

Start at `docs/README.md`. The specs in `docs/specs/` are the contract: a new operation or a changed input starts there, then tests, then code.

- **Tests first** where a spec's Definition of Done describes the behaviour: write the failing test from it, run it red, then write the code. Commit the tests before the code (`test:` then `feat:`). Infrastructure (image, CI) and trying out a library's behaviour are exceptions; turn what you learn into a test afterwards.
- For any operation, read REQ-001 (`docs/specs/req-001-core.md`) and the operation's area spec; REQ-001's Requirement Rules say how they relate. For access, configuration, logging or limits, read REQ-002 (`docs/specs/req-002-service.md`).
- Which area an operation belongs to follows the rule and map in `docs/specs/README.md`, not judgement.
- Write requirement IDs in full, as the specs index says (`REQ-004-PRS-F005`, not `PRS-F005`).

## Conventions

- Conventional Commits: `feat`, `fix`, `docs`, `ci`, `chore`, `refactor`, `test`.
- Keep scripts and agents off `api.github.com` (60 requests/h unauthenticated): use `git ls-remote`, `raw.githubusercontent.com`, `releases.atom`.
- Markdown: one line per paragraph, no hard wrapping. `mdformat` formats it (config in `.mdformat.toml`).
- Commit or push only when the operator asks.
