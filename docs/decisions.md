# Architecture decisions

## Thin typed client, not a navigable domain model

v1 exposes one client class whose methods map ~1:1 to API endpoints, each
returning typed models with a raw-payload escape hatch.

The API is undocumented and its behavior (pagination, optional fields) is
still being learned; explicit I/O keeps every HTTP request visible so callers
own retries and caching, and pure parse functions stay testable against
recorded fixtures. A lazy-fetching domain layer
(Site → Board → Meeting) hides I/O and locks in design guesses too early —
it can be added later on top of the client without breaking anything.

## Lenient two-tier parsing on frozen dataclasses, no pydantic

Each model declares a tiny set of load-bearing fields (ids, dates) whose
absence raises a typed payload error; every other field is best-effort
Optional and never raises. Models are frozen dataclasses carrying the raw
response dict; parsing is hand-written pure functions.

The upstream API is undocumented and makes no compatibility promises, so
strict schema validation would turn every cosmetic upstream change into a
caller-facing crash — strictness against a schema we don't control is a
liability, not a safety feature. The `raw` dict is the contract with the
future: new upstream fields are reachable immediately and modeled in a later
minor release. Pydantic was rejected because its value is exactly the
validation we don't want, at the cost of a heavy dependency; hand-written
parse functions keep the runtime dependency footprint at httpx alone and put
each lenient/strict decision in plain sight. Library semver covers the
library surface only; upstream drift is detected by an opt-in live contract
test suite and handled in releases.

## Polite pacing by default; retries and caching stay caller-owned

The client enforces a minimum interval between requests
(`min_request_interval`, default 0.25 s, `0` disables); it still ships no
retries or caching.

CivicClerk tenants are small municipal servers with no observed rate
enforcement, and one unfiltered listing call can fan out to hundreds of
paged requests — a docs-only recommendation protects the service only when
users read docs. Well-regarded clients of unenforced services pace
proactively by default (PyGithub `seconds_between_requests=0.25`, added
after users tripped abuse detection in the wild; scrapelib, built for
state-legislature scraping, defaults to 60 requests/minute), and every
request now carries this library's name in its User-Agent, so misbehavior
is attributable to the library. The gate lives in the client (not the
httpx transport) so injecting a client for unrelated reasons does not
silently shed politeness — disabling is an explicit constructor argument.
Retries and caching remain caller policy: they are the genuinely subtle,
use-case-dependent pieces, and a configured `httpx.Client` (or a wrapper
library such as `careful`) can be injected to supply them. `careful` was
considered for the pacing itself and rejected inside the library: pre-1.0
API, adds a transitive dependency (structlog) against the httpx-only
footprint, and two of its three features are ones we deliberately leave to
callers.

## Naive wall-clock datetimes — no upstream timezone source exists

Model datetimes are naive local wall-clock values, and the library makes no
attempt to attach a timezone.

The API stamps a `Z` (UTC) suffix on datetimes that are actually local
wall-clock times (a 7 pm meeting arrives as `19:00:00Z`), and nothing
upstream reliably declares the tenant's timezone: the OData `$metadata`
shows the only timezone-typed fields are `secondaryIanaTimeZone` /
`secondaryAbbreviatedTimeZone` on events — observed empty across five
public tenants in five US states (2026-07-14) — and the `Settings` entity
carries only portal display labels. Deriving a zone from the event
location's address would bake in per-tenant geography guesses, which the
tenant-generic rule forbids. Callers who need aware datetimes attach the
municipality's timezone themselves; re-verify with the live suite before
revisiting.

## Tenant-generic by construction

The client takes the CivicClerk site subdomain as its only required
constructor argument, and no municipality-specific policy (file-naming
conventions, agenda-title parsing, meeting-selection rules) lives in the
library. Such policy varies per municipality and per consuming tool; baking
any one municipality's rules in would misparse every other tenant. Recorded
test fixtures are scrubbed to fictional tenants for the same reason.
