# Keycloak as authorization server

| Meta | Value |
| :- | :- |
| **Date** | 2026-10-26 |
| **Author** | loxy (drafted with Claude) |
| **Status** | Draft: steps 2, 3, 5 and 6 come from a working setup with Keycloak 26.8.1 (October 2026); step 4 is untested; nothing yet repeated with Erpel itself |

Erpel works with any authorization server that issues JWT access tokens it can check ([ADR-003](../arc42/adr/ADR-003-local-token-check.md)). This guide shows one way to set up Keycloak for one MCP client. A second client (another agent) gets its own Keycloak client, agent identity and Erpel instance. Names below are placeholders.

## 1. The agent identity

- Create a user for the agent in the realm, used for nothing else. Its ID is `ERPEL_SUBJECT`.
- Give it a realm role that only agent identities have, for example `mcp-agent`. Step 4 uses it.
- Require a second factor for it (OTP or WebAuthn). Erpel checks who a token is for, not how the sign-in happened.

## 2. The client

Pre-register one **public** client per MCP client, instead of letting the MCP client register itself:

- Client ID: for example `erpel-agent`; this is `ERPEL_CLIENT_ID`. Enter it in the MCP client's settings (for Claude: "Use your own OAuth client").
- Standard flow only: no direct access grants, no implicit flow, no service account.
- PKCE required with `S256` (Advanced: "Proof Key for Code Exchange Code Challenge Method").
- Valid redirect URIs: exactly the MCP client's callback (for Claude, `https://claude.ai/api/mcp/auth_callback`), no wildcards.
- Restrict anonymous client registration in the realm (Client registration policies), so a client that tries dynamic registration can't create clients.

## 3. The audience

Erpel requires its resource URL in the token's `aud` (`ERPEL_RESOURCE_URL`, e.g. `https://erp.example.com/mcp`).

- Create a client scope with an **Audience** mapper whose "Included custom audience" is the resource URL, "Add to access token" on.
- Add the scope to the client as a default scope.

Keycloak's RFC 8707 resource indicators are an experimental feature (`resource-indicators`). It isn't needed: in one observed setup, Keycloak 26.8.1 accepted the `resource` parameter Claude sends without the feature turned on, and the Audience mapper put the URL into `aud`. Tokens may carry further audiences (Keycloak adds `account`); Erpel accepts that as long as its own URL is among them.

## 4. Only the agent signs in through this client

A browser that already holds a person's Keycloak session signs the MCP client in as that person, without showing a login form. Erpel's subject check refuses that token, but the client only sees a failed sign-in and may retry many times. Stop it at Keycloak:

The check must run after the user is known, on both paths: a fresh login and an existing session cookie. In Keycloak's standard browser flow the cookie step ends the flow on its own, so a check inside the login forms misses the case that matters. Build a separate flow instead:

```
erpel browser (top level)
├── Authenticate                      sub-flow, Required
│   ├── Cookie                        Alternative
│   └── Forms                         sub-flow, Alternative
│       ├── Username Password Form    Required
│       └── OTP Form                  Required   (the second factor)
└── Agent only                        sub-flow, Conditional
    ├── Condition - User Role         Required   role: the agent role, "Negate output" on
    └── Deny Access                   Required
```

- Bind the flow to this client only (Client → Advanced → Authentication flow overrides → Browser flow).
- Check it: sign in to the realm as a person in a browser, then connect the MCP client from the same browser; Keycloak must deny access instead of issuing a token.

The two fences then are Keycloak's flow (first) and Erpel's subject check (second).

## 5. Scopes

Erpel publishes `ERPEL_REQUIRED_SCOPES` (default `openid`) as `scopes_supported` in its protected resource metadata. A client that finds none there requests every scope in Keycloak's metadata, and Keycloak refuses the sign-in with `invalid_scope` for any scope the client isn't allowed. Keycloak always allows `openid`. Leave the scopes a client requests on its own (Claude asks for `offline_access`) assigned to the client as optional scopes; removing them would likely break its sign-in.

## 6. Token and session lifetimes

The second kill switch (disabling the agent identity in Keycloak) acts when the current access token expires, so keep access tokens short:

- **Access token lifespan:** minutes; Keycloak's default of 5 minutes works, and clients refresh without asking the person.
- **Offline sessions:** a client that requests `offline_access` holds an offline token, which outlives the login session; signing out of Keycloak doesn't end it. Set the client's offline session idle and maximum times (Client → Advanced), for example 7 days unused and 30 days in total.
- **Stopping the agent:** disable the user, or sign out its offline sessions (Users → the agent → Sessions). Either ends refreshes; the current access token lives out its lifespan.

## 7. Values for Erpel

```sh
ERPEL_ISSUER=https://id.example.com/realms/example
ERPEL_JWKS_URL=https://id.example.com/realms/example/protocol/openid-connect/certs
ERPEL_CLIENT_ID=erpel-agent
ERPEL_SUBJECT=00000000-0000-0000-0000-000000000000
ERPEL_REQUIRED_SCOPES=openid
```

Keycloak's tokens carry the client in `azp` and the claim `typ` `Bearer`, both of which Erpel accepts. Keycloak must be reachable from the MCP client's backend (for a hosted client, from the internet) and from Erpel (JWKS).

## References

- [Configuration](configuration.md)
- [Keycloak: MCP authorization server](https://www.keycloak.org/securing-apps/mcp-authz-server)
- [ADR-003](../arc42/adr/ADR-003-local-token-check.md)
