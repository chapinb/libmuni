# libcivicclerk v1 — thin typed client for the CivicClerk public API

## Goal

A general-purpose, read-only Python library for the CivicClerk API (the
meeting-portal platform used by many municipalities at
`{tenant}.api.civicclerk.com`). Today, anyone who wants meeting data from a
CivicClerk portal must reverse-engineer the undocumented OData API themselves.
This library gives tool builders a small, trustworthy client: typed models,
explicit I/O, and the API's sharp edges already handled.

## User stories

End-user stories (what data must be reachable through the library):

1. Calendar — a resident can see upcoming and past meetings for a
   municipality, optionally filtered to a board/committee.
2. Attendance — a resident can see how to attend a meeting: physical
   location, virtual meeting link, recording of a past meeting, as available.
3. Materials — a resident can see a meeting's published materials: agenda,
   packet, minutes, supporting documents.
4. Agenda structure — a resident can browse the structured agenda
   (sections → items → attachments), not just an agenda PDF.
5. Documents — a resident can reliably download any published document.

Developer stories (the library surface):

1. Create a client for any CivicClerk tenant by site subdomain.
2. List event categories (boards/committees) for a site.
3. List events filtered by category and/or date range, as typed models with
   real timezone-aware datetimes (not bare dates), so calendars and iCal
   feeds built on them are correct.
4. Fetch the structured agenda for a meeting and walk its tree.
5. Resolve a durable download URL or stream bytes for any file/attachment,
   with known quirks handled.
6. Fetch a document's plain text (where the API provides it) for indexing
   and search.
7. Distinguish "tenant does not exist" from "tenant has no data" — typos
   fail loudly at client construction or first call.
8. Reach raw payload fields the models don't cover (escape hatch).
9. Get distinct, typed errors; "not published yet" is an empty state, not an
   error.
10. Use everything without credentials (public API only).

## Requirements

- A client is constructed from a tenant subdomain; every public method maps
  to exactly one HTTP request and returns typed models.
- Event categories, events (with category and date filtering), structured
  agendas, and file downloads are all reachable.
- Event times are timezone-aware datetimes preserving what the API provides.
- Every model exposes the raw response dict it was parsed from.
- Parsing is pure (JSON dict in, models out) and tested against recorded
  fixtures without HTTP mocking.
- Typed exception hierarchy distinguishes transport/HTTP errors, unknown
  tenants, and unparseable payloads; absent optional data yields None/empty,
  never raises.
- An opt-in live contract test suite (marked, excluded by default) hits a
  real tenant to detect upstream schema drift.
- Package is PyPI-publishable: metadata, license, README with a quickstart.

## Out of scope

- Authenticated/write endpoints (comments, subscriptions, admin).
- A navigable lazy-fetching domain layer (possible later, atop this client).
- Caching, retries, rate limiting — callers own their HTTP policy.
- Any municipality-specific logic (agenda-title parsing, file-name policy,
  meeting-selection rules); those belong in consuming applications.
- Async client (revisit after v1 if demand exists).
- Search, iCal generation, CLI, municipality discovery — application
  concerns built on top of this library, not part of it.

## Constraints

- No references to any specific municipality or private project in code,
  docs, tests, or examples — use invented tenant names in examples. Recorded
  fixtures must be scrubbed to a fictional tenant before commit.
- Two-tier typing policy: each model has a tiny set of load-bearing fields
  (ids, dates) whose absence raises a typed payload error naming the field;
  every other field is best-effort Optional, never raising. Models are
  frozen dataclasses with a `raw` dict; no pydantic (validation strictness
  against an uncontrolled schema is a liability — see docs/decisions.md).
- Semver covers the library surface, not the upstream API; upstream drift is
  detected by the live contract suite and handled in releases. Say so in the
  README.
- README carries an affiliation disclaimer (not affiliated with, endorsed
  by, or supported by CivicPlus), a polite-usage note, and a note that
  redistribution questions for downloaded documents belong to downstream
  applications.
- The public surface must be self-documenting: descriptive names that read
  as the domain (no abbreviations), complete type hints, keyword-only
  optional parameters, docstrings on every public symbol that state units,
  timezone semantics, and failure modes. A developer should be able to use
  the library correctly from signatures and docstrings alone.
- MIT license. Python 3.11+ (CI matrix 3.11–3.13).
- Modern Python tooling: uv-managed project, ruff (lint + format), ty,
  pytest, prek-managed pre-commit hooks; src layout; package/import name
  `libcivicclerk`.
- GitHub Actions CI validates hooks (prek run --all-files), type check,
  tests across the version matrix, and a wheel/sdist build. No publishing.
- HTTP via httpx; the client accepts an optional injected `httpx.Client`.
- Known API facts that bind the implementation:
  - Base: `https://{tenant}.api.civicclerk.com/v1`, public, no auth.
  - Events: `GET /v1/Events` with OData `$filter`/`$orderby`; event payloads
    carry `eventDate`, `agendaId` (0 = no structured agenda yet), and
    `publishedFiles` (each with `fileId`, `type`, `name`, `publishOn`).
  - Categories: `GET /v1/EventCategories` (name field is `categoryDesc`);
    `/v1/Categories` does not exist.
  - Structured agenda: `GET /v1/Meetings/{agendaId}` path-style only —
    paren-style `/Meetings(id)` and `/Sections` are not public. Agenda
    attachment fields are `id` / `fileName` / `isLink` (links have no file).
  - Downloads: meeting-level files download via
    `GetMeetingFileStream(fileId=...,plainText=false)`. Agenda attachment ids
    collide in that endpoint's namespace and can resolve to unrelated files;
    an attachment's `pdfVersionFullPath` signed URL is authoritative when
    present.
  - `GetMeetingFileStream`'s `plainText=true` behavior is unverified — spike.

## Environment

- `uv sync` to install; `uv run pytest` for tests (live suite excluded by
  default, opt in with `-m live`); `uv run ruff check` and
  `uv run ruff format --check` for lint/format; `uv run ty check` for types;
  `prek run --all-files` for the full hook suite.
- CI: GitHub Actions workflow running the same commands on 3.11–3.13.

## Decision log

- 2026-07-13: Thin typed client over a navigable domain model for v1 — see
  docs/decisions.md.
- 2026-07-13: Independent design; no external project's use cases are hard
  requirements.
- 2026-07-13: Package name `libcivicclerk` to match the repository; check
  PyPI availability during the scaffold slice and revisit only if taken.
- 2026-07-13: Lenient two-tier parsing on frozen dataclasses; no pydantic —
  see docs/decisions.md.
- 2026-07-13: MIT license; Python floor 3.11; CI validates only (no PyPI
  publish workflow in v1).
- 2026-07-13: PyPI name `libcivicclerk` confirmed available (404 on the
  package JSON endpoint).
- 2026-07-13: ruff and ty run as local prek hooks via `uv run` (pinned to
  the project's dev-group versions) rather than remote hook repos; prek's
  native hooks cover the generic checks.

## Deferred

- Navigable domain layer (Site → Board → Meeting) built on the client.
- Async client variant.
- Auth-required API surface.
- Change detection helpers (stable-identity diffing; check whether the API
  honors If-None-Match / If-Modified-Since — cheap spike later).
- Structured minutes/actions (motions, votes) if the API exposes them
  post-meeting.
- PyPI trusted-publishing release workflow.

## Done criteria

- All developer stories exercisable against a live tenant in a quickstart
  script, and against recorded fixtures in the test suite.
- Hooks, lint, format, type check, and tests all pass via the Environment
  commands, locally and in CI.
- README documents install, quickstart, the error model, the semver stance,
  and the affiliation disclaimer.
- Version 0.1.0 buildable as a wheel/sdist with clean PyPI metadata.

## Slices

- [x] 1. Scaffold: uv project `libcivicclerk` (src layout, ruff, ty, pytest,
  prek hooks, MIT license, README stub with disclaimer, CLAUDE.md) plus
  GitHub Actions CI (hooks, types, tests on 3.11–3.13, build); importable
  empty package; suite green locally. Touches pyproject.toml, .github/,
  .pre-commit-config.yaml, src/libcivicclerk/, tests/.
- [ ] 2. Tracer bullet: client construction for a tenant +
  `get_event_categories()` returning typed `EventCategory` models via a pure
  parse function; fixture test proves parsing end to end. Touches
  src/libcivicclerk/client.py, models.py, parsing, tests/fixtures.
- [ ] 3. Error model: exception hierarchy (transport/HTTP, unknown tenant,
  payload) with the two-tier load-bearing-field policy and `raw` escape
  hatch established as conventions; tenant typos fail loudly. Touches
  errors.py, client.py, models.py, tests.
- [ ] 4. Events: `get_events(category_id=None, from_date=None, to_date=None)`
  returning typed `Event` models with timezone-aware datetimes and
  `published_files`; fixture tests cover filter combinations, empty results,
  and datetime edge cases. Touches client.py, models.py, tests.
- [ ] 5. Attendance-field spike→slice: capture real Events payloads, identify
  location / virtual-join / recording fields, model what exists on `Event`
  (absent → None); record findings in this spec's decision log. Touches
  models.py, fixtures, tests.
- [ ] 6. Pagination spike→slice: determine OData paging behavior on large
  Events result sets and make `get_events` return complete results (or
  expose paging explicitly); record findings. Touches client.py, tests.
- [ ] 7. Structured agenda: `get_agenda(agenda_id)` returning a typed agenda
  tree (sections/items/attachments) plus a flattening walk helper; fixture
  covers nesting, links, and empty agendas. Touches client.py, models.py,
  tests.
- [ ] 8. Downloads: durable URL resolution and byte streaming for meeting
  files and agenda attachments, preferring `pdfVersionFullPath` and guarding
  the attachment-id collision. Touches client.py, models.py, tests.
- [ ] 9. Plain-text spike→slice: verify what `plainText=true` returns from
  `GetMeetingFileStream`; expose text retrieval if usable, else record the
  finding and drop the story. Touches client.py, tests.
- [ ] 10. Live contract suite: opt-in `live`-marked tests covering each
  endpoint against a real tenant, excluded by default, documented for
  scheduled CI use. Touches tests/, pyproject.toml, README.
- [ ] 11. Release readiness: README quickstart, semver stance, disclaimer
  text finalized; PyPI metadata; version 0.1.0; wheel/sdist build verified.
  Touches README.md, pyproject.toml.
