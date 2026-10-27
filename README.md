# Erpel

An MCP server for ERPNext with hard limits: a short, fixed list of tools, tokens from an external OAuth authorization server, and only the rights of one ERPNext user.

**Status:** early development, not usable yet.

## What it is

- **A separate service**, not a Frappe app. It calls ERPNext's REST API with the API key of a dedicated agent user and holds no other ERPNext credential. Whatever the service does, ERPNext's role for that user is the upper limit.
- **A resource server** for the MCP authorization spec. It serves the protected resource metadata, answers a missing token with 401, and checks every access token itself (issuer, audience, client, subject). Sign-in happens at an external authorization server such as Keycloak.
- **A fixed list of operations**, each with its own purpose and input schema, read and write separated. No generic document access, method calls or file access.
- **Client-neutral.** It speaks plain MCP (Streamable HTTP) and doesn't rely on any client asking before a write.

## What it is not

- Not a general ERPNext API bridge: tools that take a DocType, method name or field list as input are out of scope.
- Not affiliated with or endorsed by Frappe Technologies. ERPNext and Frappe are their trademarks.

## Documentation

Start at [docs/README.md](docs/README.md). The most important parts:

- [Requirement specifications](docs/specs/README.md): the core, and the operations by accounting area
- [Architecture](docs/arc42/README.md) and [decisions](docs/arc42/adr/README.md)
- [Configuration](docs/guides/configuration.md)

## Licence

[Apache-2.0](LICENSE). Why: [ADR-006](docs/arc42/adr/ADR-006-licence-and-name.md).
