# Security policy

Enterich holds an ERPNext API key and decides what an AI agent may do with it, so we take reports about it seriously.

## Reporting a vulnerability

Report it privately through GitHub's private vulnerability reporting: [report a vulnerability](https://github.com/interlusion/enterich/security/advisories/new) (the repository's Security tab). Please don't open a public issue, pull request or discussion for it.

A useful report says:

- the Enterich version (the image tag, or better its digest) and the ERPNext version;
- what an agent, a client or anyone else can do that they shouldn't, and how;
- the steps or requests that show it, with the configuration that matters, never real keys, tokens, hostnames or business data.

## Scope

In scope is anything that breaks what Enterich promises in its [core](docs/specs/req-001-core.md) and [service](docs/specs/req-002-service.md) specifications, for example:

- **The token check:** a request that gets through without a valid access token for the configured issuer, audience, client and subject, or with an expired one; protected resource metadata that names another authorization server than the configured one.
- **The tool limits:**
  - making Enterich send ERPNext a request its specs don't catalogue, for example through a name input;
  - submitting, cancelling, amending, deleting or discarding a document, or changing one that isn't a draft;
  - reaching another company's data;
  - calling a tool the configuration (`ENTERICH_TOOLS`) doesn't offer;
  - getting past the limits on input, result size and time.
- **Outside text:** text from outside parties (customers, suppliers, banks) returned anywhere but in `outside_text`, or more of ERPNext's error than Enterich forwards, so an agent could mistake it for instructions.
- **Secret handling and the log:** an ERPNext key or secret, or an access token, appearing in a log, a result, an error or anywhere else outside Enterich; an operation logged without its caller, or a log line a caller can forge.
- **Configuration:** a setting Enterich accepts although its rules refuse it, such as an issuer over plain HTTP.
- **The docs:** a guide whose instructions leave a deployment open, such as rights it tells you to grant.

Out of scope:

- ERPNext and Frappe themselves, and the authorization server (for example Keycloak): report those to their projects.
- A deployment that grants the agent user more than the configuration guide says, or what an agent does within the tools offered and the ERPNext rights granted.
- An agent following instructions found in data that Enterich did mark as outside text: Enterich tells the agent to treat it as data, and drafts wait for a person.
- Denial of service by sheer volume against an instance, which the platform in front of Enterich limits.

## Supported versions

Only the latest minor version gets security fixes. A fix is released as a patch of it as soon as it is ready, with a **Security** heading in the changelog and a GitHub security advisory published with the release ([releasing guide](docs/guides/releasing.md)). While Enterich is at 0.x, a minor version may break the interface, so taking a fix can mean taking those changes too; the changelog says which.

## What to expect

Enterich is maintained on a best-effort basis: we answer and fix as soon as we can, without a promised time. There is no bounty. With your consent, the advisory credits you.
