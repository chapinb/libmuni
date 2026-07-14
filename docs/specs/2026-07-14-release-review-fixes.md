# Release-review fixes

## Goal

Close the initial-release blockers found by adversarial review: document all
attacker-influenced request targets, preserve existing files when downloads
fail, keep malformed JSON inside the typed error hierarchy, and prevent signed
URL credentials from entering exception text or attributes.

## Requirements

- Security documentation covers continuation links and redirects in addition
  to attachment URLs.
- A failed save leaves an existing destination byte-for-byte unchanged and
  leaves no temporary artifact; a successful save replaces the destination.
- JSON endpoint responses must be objects, and collection fields consumed by
  the client must be arrays; structural violations raise `PayloadError`.
- Exception-visible URLs retain useful origin and path context while omitting
  userinfo, query strings, and fragments.
- The library emits no logs of its own; callers retain observability through
  typed exceptions and their configured HTTP client.

## Out of scope

- Preventing or restricting the already documented SSRF behavior.
- Adding retries, caching, response-size limits, or a logging framework.
- Changing public method signatures or exception classes.
- Fixing unrelated review observations.

## Constraints

- Use test-first Red-Green-Refactor mechanics.
- Preserve the existing single-pass streaming interface and same-filesystem
  atomic replacement behavior.
- Temporary files must be created beside the destination so replacement stays
  atomic across filesystems.
- Raw signed URLs remain available on models, but never appear in errors.
- Maintain Python 3.11 support and the existing httpx-only runtime dependency.

## Environment

- `uv run pytest` runs the offline suite.
- `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check`
  enforce static quality.
- `uv build` and `uv run --group docs mkdocs build --strict` validate release
  artifacts and documentation.

## Decision log

- Require mapping-shaped JSON at the response boundary because every consumed
  CivicClerk JSON endpoint contract is object-shaped; ambiguity is less safe
  than surfacing upstream drift as `PayloadError`.
- Keep logging caller-owned. A library log stream would duplicate httpx and
  application observability while increasing the chance that signed URLs are
  persisted; safe typed exceptions are the diagnostic boundary.
- Redact all URL userinfo, query, and fragment data rather than attempting to
  maintain an incomplete allowlist of sensitive parameter names.

## Deferred

- Host-restricting continuation links and redirects remains a documented trust
  posture decision rather than part of this change.

## Done criteria

- Focused regression tests fail before and pass after each behavior change.
- The full offline suite and all static, build, and documentation checks pass.
- Security and usage documentation match the implemented failure behavior.
- Changes are split into logical reviewable commits.

## Slices

- [x] 1. Preserve destinations with atomic temporary-file saves, proven by interrupted-overwrite and successful-replacement tests; touches streams and download tests.
- [ ] 2. Validate JSON response and collection shapes as `PayloadError`, proven by malformed top-level and `value` tests; touches client and error tests.
- [ ] 3. Redact sensitive URL components from all exception diagnostics, proven across HTTP, network, and empty-stream failures; touches errors, client, streams, and tests.
- [ ] 4. Expand the security and usage documentation to cover continuation links, redirects, safe diagnostics, and caller-owned logging; touches documentation.
