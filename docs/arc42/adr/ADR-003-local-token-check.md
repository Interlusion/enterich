# ADR-003: Local JWT check for one agent identity, 5 s clock leeway

| Meta | Value |
| :- | :- |
| **Status** | Accepted |
| **Date** | 2026-10-24 |
| **Author** | loxy (drafted with Claude) |

## Context

Enterich's MCP path is reachable from the internet, so the token check is its gate ([REQ-002-URS-NF001](../../specs/req-002-service.md#req-002-urs-nf001-only-the-agent-identity-gets-in)). Three observations from the spike shape it:

- **A person's session gets a token through the agent's client.** A browser signed in to the realm as a person reconnected the client; Keycloak issued a token for that person, and only Enterich's subject check refused it.
- **The client then retried about 50 times within minutes.** Rejections must be cheap and their log lines short.
- **Clients hold refresh or offline tokens.** Signing out ends nothing; the kill switches are disabling the user in ERPNext (next request) and at the authorization server (once the access token expires).

The spike verified tokens locally with PyJWT against the realm's JWKS, with 30 s clock leeway. The leeway adds directly to the second kill switch.

## Decision

- **Local verification of JWT access tokens** against the issuer's JWKS, no token introspection. The checks are those of REQ-002-PRS-NF001: algorithm allowlist (asymmetric only, default RS256), signature, issuer, audience (Enterich's resource URL), client (`azp`, or `client_id` per RFC 9068), subject, access-token marker, times, size. Keys come only from the configured JWKS URL, never from a token's headers.
- **Both `azp` and `client_id` are accepted** for the client, so tokens of RFC 9068 authorization servers work as well as Keycloak's; when a token carries both, they must be equal.
- **The verifier hands the SDK `expires_at = exp + leeway`.** The SDK's bearer middleware refuses a token once `expires_at` has passed, without leeway of its own. Enterich sets `AuthSettings.validate_token_resource` explicitly instead of relying on its changing default, because the verifier checks `aud` itself.
- **One agent identity per instance:** one client and one subject, configured. A second identity runs a second instance with its own ERPNext agent user. The identity may be a user who signs in through the client (authorization code with PKCE) or the client's own service account (client credentials); Enterich checks the same claims either way.
- **Clock leeway 5 s by default, configurable from 0 to 60 s.** Enterich and the authorization server are expected to run with synchronised clocks; 5 s covers small drift. The leeway is logged at start.
- **JWKS cached for 5 minutes**; an unknown `kid` refetches at most once per 30 s, and otherwise fails as a rejection. When the cache has expired and a refresh fails, no keys are usable.
- **A refused token is a 401; an unavailable JWKS is a 503.** A 401 tells a client to sign in again, which can't help when Enterich can't reach the keys, and invites the retry storm seen in the spike. With no usable keys, Enterich answers 503 with `Retry-After`; the verifier raises, and Enterich's outer wrapper turns that into the 503.
- **Rejections log one line,** written by Enterich's outer wrapper from the response status (ADR-002), so a missing token and a missing scope are logged too: the reason category, and `sub` and client when the signature was valid. Unsigned header values are quoted, never logged raw.
- **Second factors are the authorization server's job.** Enterich checks who the token is for, not how the person signed in.

## Alternatives Considered

### Alternative 1: Token introspection (RFC 7662) on every request

The authorization server answers per token whether it is active, so disabling the user takes effect at once.

**Rejected because**: one call to the authorization server per request, and Enterich then needs a client secret of its own. The ERPNext switch already acts on the next request, and the token switch is bounded by the access token lifetime plus the leeway. Keycloak's default lifetime is 5 minutes; other servers issue tokens for an hour, so the deployment keeps it short.

### Alternative 2: A list of allowed subjects or clients in one instance

**Rejected because**: every identity would share one ERPNext agent user, so ERPNext couldn't tell the agents apart and one couldn't be stopped alone. Mapping identities to keys is a later step (backlog), if ever.

### Alternative 3: The spike's 30 s leeway

**Rejected because**: it lengthens the authorization-server kill switch for no gain when clocks are synchronised.

## Consequences

### Positive

- No network call per request; rejections cost a signature check at most.
- The kill switches are bounded and documented: ERPNext at once, the authorization server within the token lifetime plus 5 s.
- An outage between Enterich and the authorization server doesn't send clients back to sign in.

### Negative

- A disabled identity keeps working until its access token expires, and Enterich doesn't bound that lifetime itself.
- The deployment must keep clocks synchronised; drift over 5 s causes rejections of fresh tokens.

## Reconsideration Triggers

Revisit this decision when:

1. A deployment needs the authorization-server switch to act at once.
2. An authorization server issues opaque (non-JWT) access tokens.
3. Several identities need different tools in one instance.
4. A deployment needs Enterich itself to require a sign-in method (`acr`).

## Compliance

- Enterich SHALL verify every request's token itself and SHALL NOT cache an authorization decision.
- The leeway SHALL NOT exceed 60 s.
- Symmetric algorithms and `none` SHALL NOT be accepted.
- Signing keys SHALL come only from the configured JWKS URL, over HTTPS.

## References

- [RFC 9068: JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662: Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- [REQ-002: Enterich service requirement specification](../../specs/req-002-service.md): REQ-002-URS-NF001, REQ-002-URS-NF004, REQ-002-PRS-NF001, REQ-002-PRS-NF007, REQ-002-PRS-NF009
