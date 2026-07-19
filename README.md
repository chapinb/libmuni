# libmuni

Unofficial read-only Python clients for municipal government software
platforms. A municipality's public record is spread across several vendor
platforms, and libmuni provides one small, typed, well-behaved client per
platform. The clients share no cross-vendor data model — what unifies them is
the jurisdiction rather than a schema.

The first platform is **CivicClerk** (`libmuni.civicclerk`), a meeting-portal
system used by many municipalities to publish meeting calendars, agendas,
minutes, and supporting documents. Those portals are backed by a public,
unauthenticated API at `https://{tenant}.api.civicclerk.com/v1`; the client
reads that data — meeting calendars, attendance details, structured agendas,
and document downloads — without reverse-engineering the API yourself.

## Install

```sh
pip install libmuni
```

Requires Python 3.11+. The only runtime dependency is
[httpx](https://www.python-httpx.org/).

## Quickstart

The tenant name is the subdomain of a municipality's CivicClerk portal —
the `exampletown` in `exampletown.portal.civicclerk.com`. Open a client as a
context manager and list the next month of meetings:

```python
import datetime as dt

from libmuni.civicclerk import CivicClerkClient

with CivicClerkClient("exampletown") as client:
    for event in client.iter_events(
        from_date=dt.date.today(),
        to_date=dt.date.today() + dt.timedelta(days=30),
    ):
        print(event.starts_at, event.name)
```

`iter_events` is lazy and pages for you, 15 events at a time. **With no date
range it walks the tenant's entire meeting history** — potentially thousands of
events and hundreds of requests — so pass `from_date`/`to_date` for anything
interactive. Wrap the call in `list(...)` when you want every match up front.

The rest of the surface, in brief — each snippet runs inside that `with`
block, picking an `event` (and its `file`/`attachment`) from a listing:

```python
# Boards and committees; pass category_id= to iter_events to filter meetings
for category in client.get_event_categories():
    print(category.id, category.name)
```

```python
# How to attend or watch a meeting — both None when the portal has neither
print(event.virtual_meeting_url)  # Zoom/Teams join link
print(event.recording_url)        # YouTube if uploaded, else the direct stream
```

```python
# A meeting's structured agenda, flattened into display order
agenda = client.get_agenda(event.agenda_id)  # agenda_id is None until published
for item in agenda.walk_items():
    print(item.name)
```

```python
# Documents: meeting-level files, and per-agenda-item attachments
from pathlib import Path

client.download_file(file.file_id, Path("packet.pdf"))
client.download_attachment(attachment, Path(attachment.file_name or "file.pdf"))
text = client.get_file_text(file.file_id)  # best-effort extraction, or None
```

The [usage guide](https://chapinb.com/libmuni/latest/usage/) walks through
filtering to a board, reading agendas, and downloading documents in full — and
the [cheat sheet](https://chapinb.com/libmuni/latest/cheatsheet/) is the whole
surface on one page.

Every model keeps the raw API object in `.raw`, so fields the library
doesn't model yet are still reachable.

### Command line

The package installs a `muni-cli` command that routes to a subcommand per
platform. `muni-cli civicclerk demo exampletown` narrates a tour of the whole
CivicClerk surface, and the other subcommands (`categories`, `events`,
`agenda`, `text`, `download`) mirror the client methods, with `--json`
exposing raw payloads.

### Datetimes are local wall-clock time

The API stamps a `Z` (UTC) suffix on datetimes that are actually local
wall-clock times, and nothing in the payload declares the tenant's
timezone. The library therefore returns **naive** datetimes carrying the
local reading (a 7 pm meeting is `19:00`, whatever the timezone). If you
need aware datetimes, attach the municipality's timezone yourself.

### Errors

Every operational error subclasses `CivicClerkError`:

- `UnknownTenantError` — the tenant subdomain doesn't exist (typo?)
- `NotFoundError` — an id-parameterized lookup (agenda, file) has no data
- `APIStatusError` — any other HTTP error status
- `NetworkError` — DNS/connection/timeout failures
- `PayloadError` — a response body the library can't use

Two Python built-ins stay outside that hierarchy by design: `ValueError`
for an invalid tenant or argument, and `OSError` for a failed local file
write.

Absent optional data is never an error: an event with no published
materials has an empty `published_files`, not an exception.

## Documentation

The [cheat sheet](https://chapinb.com/libmuni/latest/cheatsheet/)
is the fastest way into the
[full documentation](https://chapinb.com/libmuni/latest/) — the
whole public surface, the traps, and what the library deliberately does not
do.

Using an LLM or coding agent? Hand it
[llms-full.txt](https://chapinb.com/libmuni/latest/llms-full.txt),
which is the entire documentation set — signatures included — as a single
file. An [llms.txt](https://chapinb.com/libmuni/latest/llms.txt)
index is served alongside it in the [llms.txt](https://llmstxt.org/) format.

## Versioning

Semantic versioning covers **this library's surface only**. The upstream
CivicClerk API is undocumented and makes no compatibility promises; every
model keeps the raw response payload reachable so upstream additions are
usable immediately, and upstream drift is addressed in library releases.

Drift is detected by an opt-in live contract suite: set
`CIVICCLERK_TEST_TENANT=<tenant>` and run `pytest -m live` (deselected by
default; suitable for a scheduled CI job).

## Development

```sh
uv sync                  # install with dev tools
uv run pytest            # tests (live suite excluded)
uvx prek run --all-files # lint, format, type check (what CI enforces)

uv run --group docs mkdocs serve   # preview the docs site locally
```

Documentation lives at
[chapinb.com/libmuni](https://chapinb.com/libmuni/).
Pushing a `v*` tag deploys that version's docs with a version selector
(GitHub Pages must be set to serve the `gh-pages` branch once).

## Disclaimer

This project is not affiliated with, endorsed by, or supported by CivicPlus
or the CivicClerk product. "CivicClerk" is used only to describe the API this
library talks to. The library reads publicly available government records
from small municipal servers, and paces its requests politely by default
(at most ~1 request/second; see `min_request_interval` to tune or disable).
Any redistribution of downloaded documents is the responsibility of
downstream applications.

**Acceptable use.** The portals are governed by the platform vendor's and
each jurisdiction's terms of use, which bind anyone accessing them and can
change at any time — this library neither reproduces nor tracks them. They
commonly restrict automated access and cap total requests over a window;
the default pacing bounds the instantaneous rate but not total volume.
Read the terms for the portals you query and keep your usage within them.
See [Acceptable use](https://chapinb.com/libmuni/latest/usage/#acceptable-use)
for details.

## License

MIT
