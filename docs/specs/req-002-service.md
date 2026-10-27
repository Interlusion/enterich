# REQ-002: Erpel Service — Requirement Specification

| Meta | Value |
| :- | :- |
| **Status** | Baselined |
| **Version** | 1.0 |
| **Date** | 2026-10-27 |
| **Author** | loxy (drafted with Claude) |

## Intended Use

The service around Erpel's operations: who may connect and how (an OAuth resource server for MCP over Streamable HTTP), the one ERPNext credential it holds, its configuration, its log, its limits on requests and on the wait for ERPNext, and its health endpoint.

Out of scope: issuing tokens or signing users in, including second factors; several agent identities in one instance; browser-based clients calling Erpel directly (no CORS); network access control (source ranges, rate limits per client), which belongs to the deployment.

[REQ-001](req-001-core.md) holds the personas, user stories and terms used here, and the rules for the operations.

## Requirement Rules

- SHALL = mandatory · SHOULD = recommended · MAY = optional
- Every SHALL verifiable (test / benchmark / inspection / analysis)
- One requirement = one idea

## URS — Non-Functional

#### REQ-002-URS-NF001: Only the agent identity gets in

**Description**: Erpel SHALL serve operations only to a caller presenting an access token issued for Erpel by the configured authorization server to the agent identity.

**Related User Stories**: REQ-001-P1-3, REQ-001-P1-4 | **Rationale**: A browser signed in as a person can obtain a token for that person through the agent's client; the subject check is then the only fence.

#### REQ-002-URS-NF002: Standard MCP sign-in

**Description**: An MCP client following the MCP authorization specification SHALL be able to discover the authorization server from Erpel and start the sign-in on its own.

**Related User Stories**: REQ-001-P1-1, REQ-001-P5-2 | **Rationale**: Clients start the sign-in only from a 401 that points to the protected resource metadata. A client that finds no `scopes_supported` there requests every scope the authorization server advertises, and the authorization server refuses the sign-in when the client isn't allowed one of them (`invalid_scope`).

#### REQ-002-URS-NF003: ERPNext's permissions are the hard limit

**Description**: Every call Erpel makes to ERPNext SHALL run as the agent user, and Erpel SHALL hold no other ERPNext credential.

**Related User Stories**: REQ-001-P1-3, REQ-001-P2-1, REQ-001-P5-2 | **Rationale**: No bug in Erpel can then exceed what ERPNext allows the agent user.

#### REQ-002-URS-NF004: Kill switches take effect

**Description**: Erpel SHALL stop serving the agent on the next operation after the agent user is disabled in ERPNext, and once the current access token expires after the agent identity is disabled at the authorization server.

**Related User Stories**: REQ-001-P1-4 | **Rationale**: Clients hold refresh or offline tokens, so signing out ends nothing; disabling the users must.

#### REQ-002-URS-NF005: Attribution

**Description**: Erpel SHALL record each operation with the token's subject and session, its arguments and its outcome.

**Related User Stories**: REQ-001-P1-6, REQ-001-P2-1, REQ-001-P3-1 | **Rationale**: ERPNext shows that the agent user changed a document; Erpel's log shows which connection and when.

#### REQ-002-URS-NF006: Secrets stay secret

**Description**: Erpel SHALL NOT write the ERPNext API key or secret, or any access or refresh token, to its logs, its errors or its tool results.

**Related User Stories**: REQ-001-P1-3, REQ-001-P1-4, REQ-001-P5-2 | **Rationale**: Logs travel to log stores and screens; a leaked key bypasses every limit but ERPNext's role.

#### REQ-002-URS-NF007: Client-neutral

**Description**: Erpel SHALL behave the same for every MCP client and SHALL NOT depend on a particular client.

**Related User Stories**: REQ-001-P4-1 | **Rationale**: Further clients (local models, agents without a person) are expected; client specifics belong to the authorization server's clients and the deployment.

#### REQ-002-URS-NF008: Deployment-neutral

**Description**: Everything a deployment differs in SHALL come from configuration.

**Related User Stories**: REQ-001-P5-1 | **Rationale**: One image serves every site; no site's facts go into the code.

#### REQ-002-URS-NF009: Bounded work per request

**Description**: Erpel SHALL bound the size of each request, each result and each wait on ERPNext, and SHALL keep a rejection cheap.

**Related User Stories**: REQ-001-P4-2, REQ-001-P5-3 | **Rationale**: Clients ask for the largest page unprompted; after a refused sign-in a client was seen retrying about 50 times within minutes.

#### REQ-002-URS-NF010: Operable

**Description**: The deployment SHALL be able to tell whether Erpel is running without a token and without Erpel calling ERPNext or the authorization server.

**Related User Stories**: REQ-001-P5-3 | **Rationale**: Platform probes restart a stuck instance; a probe that needs credentials or an upstream turns an upstream outage into restarts.

#### REQ-002-URS-NF011: Rights known exactly

**Description**: The deployer SHALL be able to see exactly which ERPNext rights Erpel's operations need, and which settings the authorization server must provide.

**Related User Stories**: REQ-001-P5-2 | **Rationale**: Rights granted "to be safe" widen what a manipulated agent can do; rights missing make operations fail at the site.

## PRS — Non-Functional

#### REQ-002-PRS-NF001: Token check

**Description**: Erpel SHALL accept on its MCP endpoint only a bearer access token that:

- is a JWT signed with an asymmetric algorithm from the configured list (default RS256) by a key from the configured JWKS URL, and no other source of keys (`jku`, `x5u`, `jwk` and `x5c` headers are ignored);
- carries the configured issuer as `iss` and Erpel's resource URL in `aud`;
- carries `exp` and `iat`, is not expired, not used before `nbf` and not issued in the future, each within the configured clock leeway (default 5 s, at most 60 s);
- names the configured client in `azp`, or in `client_id` when `azp` is absent; if both are present, they are equal;
- carries the configured subject as `sub`;
- marks itself as an access token: header `typ` `at+jwt` or `application/at+jwt` (compared case-insensitively), or claim `typ` `Bearer`;
- is at most 8 KiB long.

It SHALL answer a missing or refused token with 401, a token lacking a required scope with 403 `insufficient_scope`, and a token it can't check because no signing keys are available with 503 and `Retry-After: 30`.

**Related URS**: REQ-002-URS-NF001, REQ-002-URS-NF004

**Definition of Done**:

- Refused with 401: wrong issuer, audience, client, subject or key; claim `typ` ID or Refresh; no access-token marker; `azp` missing with no `client_id`; `azp` and `client_id` differing; expired beyond the leeway; `nbf` or `iat` in the future beyond the leeway; `alg` none; HS256 keyed with the public key; unknown `kid`; a `kid` with a newline (and no forged log line); not a JWT; a 9 KiB token.
- Accepted: a token expired within the leeway; header `typ` `application/at+jwt` and `AT+JWT`.
- A token with a `jku` header causes no fetch from that URL.
- Without the required scope: 403 with `insufficient_scope`.
- JWKS unreachable and no keys cached, or a JWKS without usable signing keys: 503 with `Retry-After: 30`.
- A leeway above 60 s stops Erpel at start.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF002: Protected resource metadata

**Description**: Erpel SHALL serve its protected resource metadata at the well-known path for its resource URL (RFC 9728), without authentication and whatever the request's Authorization header, with `resource` equal to the configured resource URL, `authorization_servers` holding only the issuer, `scopes_supported` listing the required scopes (default `openid`) and `bearer_methods_supported` `header`. Every 401 SHALL carry `WWW-Authenticate: Bearer` with `resource_metadata` pointing to it.

**Related URS**: REQ-002-URS-NF002

**Definition of Done**:

- A request without a token gets 401 whose `WWW-Authenticate` names the metadata URL; the metadata has the four fields with the configured values.
- The metadata is served with a garbage bearer token in the request, and with a token while the JWKS is unreachable.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF003: MCP endpoint

**Description**: Erpel SHALL serve MCP over Streamable HTTP, stateless, with JSON responses, at exactly the path of its resource URL, for the protocol revisions its pinned SDK serves: POST only, any other method (including OPTIONS) answered with 405 and `Allow: POST` before the token check, no redirect from a trailing slash, no session state between requests.

**Related URS**: REQ-002-URS-NF002, REQ-002-URS-NF007

**Definition of Done**:

- Under revisions 2025-06-18 and 2025-11-25, POST `initialize` and `tools/list` answer 200 with JSON; under 2026-07-28, a single `tools/list` exchange without `initialize` does.
- GET, DELETE and OPTIONS answer 405; the path with a trailing slash answers 404.
- Two requests to different Erpel processes behind one URL succeed in sequence without an MCP session.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF004: No client-specific behaviour

**Description**: Erpel's code SHALL NOT branch on the client's identity, User-Agent or Origin, and SHALL accept requests with any or no Origin header ([ADR-002](../arc42/adr/ADR-002-mcp-sdk-stateless-streamable-http.md) records why this departs from the MCP transport's Origin check).

**Related URS**: REQ-002-URS-NF007

**Definition of Done**:

- Requests with three different Origin values and none get the same answer.
- No code path reads User-Agent or the client name for a decision.
- Verification: test and inspection.
- Evidence: Erpel's test suite; code review at each release.

#### REQ-002-PRS-NF005: Configuration from the environment

**Description**: Erpel SHALL take its whole configuration from environment variables, validate it at start, and refuse to start with a message naming each missing or invalid variable, without printing the value of a secret. The resource, issuer and JWKS URLs SHALL use `https` (plain `http` only for a loopback host), and the resource URL SHALL be in canonical form (lower-case scheme and host, no default port, a path without a trailing slash, no query or fragment). An `http` ERPNext URL to a host other than loopback, and an `ERPEL_` variable Erpel doesn't know, SHALL each log a warning at start.

**Related URS**: REQ-002-URS-NF008, REQ-002-URS-NF006, REQ-002-URS-NF001

**Definition of Done**:

- Starting without each required variable stops Erpel with its name; an invalid URL, leeway, algorithm, time zone or operation name, or an empty scope list, stops it with name and rule.
- `http://id.example.com/…` as issuer or JWKS URL, and `https://ERP.example.com/mcp/` or `https://erp.example.com` as resource URL, stop Erpel.
- `http://erp.internal` as ERPNext URL, and a variable `ERPEL_TOOL`, each start Erpel with a warning in the `start` line.
- The message for an invalid API secret doesn't contain the secret.
- The configuration guide lists every variable; the code reads no other.
- Verification: test and inspection.
- Evidence: Erpel's test suite; the configuration guide.

#### REQ-002-PRS-NF006: One ERPNext credential

**Description**: Erpel SHALL authenticate every ERPNext call with the configured API key and secret of the agent user and no other credential, SHALL send the configured Host, SHALL NOT follow redirects from ERPNext and SHALL NOT take a proxy from the environment.

**Related URS**: REQ-002-URS-NF003, REQ-002-URS-NF006

**Definition of Done**:

- Every request the fake ERPNext receives carries `Authorization: token <key>:<secret>`, the configured Host and no cookie; a redirect from ERPNext ends as a refusal, not a second request.
- With `HTTPS_PROXY` and `HTTP_PROXY` set, requests still go directly to the configured URL.
- Verification: test and inspection.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF007: No authorization cache

**Description**: Erpel SHALL check the token on every request and SHALL keep no ERPNext session, response cache or token cache. The JWKS MAY be cached for at most 5 minutes.

**Related URS**: REQ-002-URS-NF004

**Definition of Done**:

- After the fake ERPNext starts refusing the agent's key, the next operation fails with ERPNext's refusal.
- A key removed from a JWKS that can be fetched stops being accepted within 5 minutes.
- With the JWKS unreachable, tokens signed with cached keys are accepted until the cache is 5 minutes old, then answered with 503.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF008: Log

**Description**: Erpel SHALL write its log to standard output as one JSON object per line, including lines from the libraries and the HTTP server, with the events below. `ERPEL_LOG_LEVEL` filters only the `library` lines; Erpel's own events are always written.

| Event | When | Fields besides `time`, `level`, `event` |
| :- | :- | :- |
| `start` | at start | version, resource URL, issuer, client, subject, company, leeway, offered operations, warnings |
| `operation` | each operation | operation, arguments (strings cut to 200 characters), `sub`, `sid` (null when the token has none), outcome (document number, row count, or the refusal as in REQ-001-PRS-F008), duration, number of ERPNext calls and their total duration |
| `rejection` | each rejection | status, reason, `sub` and client where the signature was valid |
| `jwks` | each JWKS fetch | outcome, number of keys |
| `error` | an unexpected exception, or a configuration Erpel refuses | operation if any, exception type, message and traceback without secrets; for a refused configuration, the problems |
| `library` | a line from a library or the HTTP server | logger, message, and the exception type and traceback if any |

**Related URS**: REQ-002-URS-NF005

**Definition of Done**:

- A test that creates a draft finds one `operation` line with the operation, `sid` and the draft's number; a refused update finds one with the refusal.
- With a fake ERPNext that delays each answer by 1 s, a create making three ERPNext calls logs 3 calls and an ERPNext duration of at least 3 s, within its total duration.
- A newline or quote in an argument doesn't break the line.
- Every captured line of a test run parses as JSON and has a known event.
- With `ERPEL_LOG_LEVEL=ERROR`, `start` and `rejection` lines are still written, and library lines below error are not.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF009: Rejection log

**Description**: Erpel SHALL log each rejection on the MCP path as one line of at most 300 characters, written from the response status so that every cause (missing token, refused token, missing scope) is covered, and SHALL NOT log rejections for other paths. It SHALL NOT fetch the JWKS more than once in 30 seconds because of unknown key IDs.

**Related URS**: REQ-002-URS-NF005, REQ-002-URS-NF009

**Definition of Done**:

- 50 requests with a token for a person's subject produce 50 lines of at most 300 characters each, and no ERPNext call; requests without a token and with a missing scope produce one line each.
- A garbage bearer token sent to `/healthz` or the metadata path produces no `rejection` line.
- Five tokens with unknown `kid` within 30 s cause at most one JWKS fetch.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF010: Nothing secret leaves Erpel

**Description**: No log line, error message or tool result SHALL contain the API key, the API secret or a bearer token, including from a failed token check or a failed ERPNext call.

**Related URS**: REQ-002-URS-NF006

**Definition of Done**:

- A test run covering every token case and every ERPNext error case finds neither the key, the secret, nor the payload or signature segment of any token used, in the captured log or in any response.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF011: Limits

**Description**: Erpel SHALL refuse request bodies over 1 MiB with 413, read at most 10 MiB of each ERPNext response, and end each ERPNext call after 30 seconds and each operation after 60 seconds.

**Related URS**: REQ-002-URS-NF009

**Definition of Done**:

- A 2 MiB POST gets 413 before token parsing; a fake ERPNext that doesn't answer produces a tool error after 30 s; a create whose calls together exceed 60 s ends with a tool error; a 20 MiB ERPNext response ends as a tool error.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF012: Health endpoint

**Description**: Erpel SHALL answer `GET /healthz` with 200 without a token and without calling ERPNext or the authorization server.

**Related URS**: REQ-002-URS-NF010

**Definition of Done**:

- `/healthz` answers 200 while the fake ERPNext and JWKS are down.
- Verification: test.
- Evidence: Erpel's test suite.

#### REQ-002-PRS-NF013: Rights listed and proven

**Description**: Every operation SHALL work with exactly the ERPNext rights its area spec lists for it, and the settings Erpel needs from the authorization server SHALL be those its token check requires (REQ-002-PRS-NF001).

**Related URS**: REQ-002-URS-NF011

**Definition of Done**:

- Every operation of the area specs has its rights listed in its area spec's Rights section.
- Run as an agent user holding exactly the listed rights, every operation works; with one listed right removed, the operations that need it fail with ERPNext's permission refusal.
- Verification: inspection and test.
- Evidence: the area specs' Rights sections; the integration test against a real ERPNext v16 site (backlog).

## Acceptance Criteria Summary

- Only tokens of the configured agent identity, for Erpel, from the configured issuer, are accepted; every token case of REQ-002-PRS-NF001 is refused; a missing token starts a client's sign-in through the metadata.
- Each operation is logged with `sub`, `sid` and outcome; no key, secret or token appears in any log, error or result.
- The whole configuration comes from the environment and is validated at start.
- Requests, ERPNext answers and waits are bounded; the health endpoint answers without credentials.

## Assumptions

Checked against Frappe v16.52 source:

- API key authentication accepts only enabled users, so disabling the agent user stops its key at the next request.

Not checked yet:

- The deployment limits who can reach Erpel's endpoint and how often; Erpel doesn't rate-limit per client.
- The authorization server issues short-lived access tokens (minutes, not hours); the second kill switch acts only when they expire.
- One Erpel instance serves one agent identity and one agent user; several identities run several instances ([ADR-003](../arc42/adr/ADR-003-local-token-check.md)).

## Open Questions

None at the moment.
