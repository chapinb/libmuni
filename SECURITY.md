# Security Policy

## Supported versions

libmuni is pre-1.0. Only the latest release on PyPI receives security
fixes; older versions do not.

## Reporting a vulnerability

Please report suspected vulnerabilities privately rather than opening a public
issue. Use GitHub's private vulnerability reporting — the **Report a
vulnerability** button on the repository's Security tab — or email
mail@chapinb.com.

Include enough to reproduce: the affected version, what you observed, and a
minimal example. You can expect an acknowledgement within a few days and an
assessment of whether the report is in scope (below) with next steps.

## Threat model and scope

libmuni is a read-only, unauthenticated client for a third-party API. It
issues no writes and stores no credentials of its own. Two behaviors are by
design and are documented on `CivicClerkClient`; treat them as the caller's
responsibility, not library bugs:

- **Attacker-influenced request targets (SSRF).** Attachment downloads follow a
  URL taken verbatim from the tenant's API response, paginated event listings
  follow the response's absolute `@odata.nextLink`, and the library-owned HTTP
  client follows redirects for every request. A malicious or compromised tenant
  can therefore point the client at internal or link-local addresses through
  any of those paths. The same injected HTTP client makes each request, so its
  custom headers may accompany a request to the attacker-selected host. Do not
  attach credentials to an injected client, isolate the network when fetching
  from tenants you do not trust, and inject a client with redirects disabled if
  your application does not need them.
- **No response-size bounds.** Downloads and JSON list responses are not
  capped; a hostile endpoint can exhaust disk or memory. Bound response size in
  your injected HTTP client or around the call.

In scope: memory-safety or injection flaws in parsing, a tenant or URL value
escaping its intended host despite validation, credential leakage the
documentation does not already call out, and denial of service not attributable
to the documented unbounded-response behavior.

Exception messages and `APIStatusError.url` omit URL userinfo, query strings,
and fragments so signed attachment credentials and continuation tokens are safe
from routine exception logging. Full signed URLs remain intentionally available
on the source models for callers that need to make the request.
