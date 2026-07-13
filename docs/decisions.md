# Architecture decisions

## Thin typed client, not a navigable domain model

v1 exposes one client class whose methods map ~1:1 to API endpoints, each
returning typed models with a raw-payload escape hatch.

The API is undocumented and its behavior (pagination, optional fields) is
still being learned; explicit I/O keeps every HTTP request visible so callers
own retries, caching, and rate limiting, and pure parse functions stay
testable against recorded fixtures. A lazy-fetching domain layer
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

## Tenant-generic by construction

The client takes the CivicClerk site subdomain as its only required
constructor argument, and no municipality-specific policy (file-naming
conventions, agenda-title parsing, meeting-selection rules) lives in the
library. Such policy varies per municipality and per consuming tool; baking
any one municipality's rules in would misparse every other tenant. Recorded
test fixtures are scrubbed to fictional tenants for the same reason.
