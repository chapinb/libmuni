---
name: verify
description: Verify libmuni end-to-end - build the wheel and drive the public API surface against a live CivicClerk tenant
---

# Verifying libmuni

The surface is the package boundary: import the **installed wheel**, not
`src/`. The library is read-only against a public API, so live verification
is safe and cheap (keep it polite — one pass, ~15 requests).

## Recipe

```sh
uv build
uv run --no-project --isolated \
  --with dist/libmuni-<version>-py3-none-any.whl \
  python <script>
```

The script should exercise, against a real tenant (get the tenant name from
the user or CIVICCLERK_TEST_TENANT — never commit one): categories, events
with a date window spanning >15 results (proves pagination), a category
filter, `get_agenda` + `walk_items`, `download_file` (assert `%PDF-` magic
and non-trivial size), `get_file_text` (str or None both fine).

Worthwhile probes: unknown tenant → UnknownTenantError; agenda id
999999999 → NotFoundError (API answers 200+empty, not 404); file id 1 →
NotFoundError with no file left at the destination; link attachment →
ValueError; inverted/far-future date windows → clean `[]`.

## Gotchas

- Event datetimes are naive local wall-clock by design — `tzinfo is None`
  is correct, not a bug.
- `get_file_text` returning None is within contract (best-effort upstream).
- An unfiltered `iter_events()` walks the tenant's ENTIRE history via
  pagination (thousands of events, hundreds of requests) — always verify
  with a date window.
