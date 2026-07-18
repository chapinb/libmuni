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
the `exampletown` in `exampletown.portal.civicclerk.com`.

```python
import datetime as dt
from pathlib import Path

from libmuni.civicclerk import CivicClerkClient

with CivicClerkClient("exampletown") as client:
    # Boards and committees
    for category in client.get_event_categories():
        print(category.id, category.name)

    # This month's meetings for one board
    events = list(
        client.iter_events(
            category_id=12,
            from_date=dt.date.today(),
            to_date=dt.date.today() + dt.timedelta(days=31),
        )
    )
    for event in events:
        print(event.starts_at, event.name)
        print("  attend:", event.location, event.virtual_meeting_url)
        print("  recording:", event.recording_url)

    # The structured agenda of the next meeting that has one
    event = next(e for e in events if e.agenda_id)
    agenda = client.get_agenda(event.agenda_id)
    for item in agenda.walk_items():
        print(("  " if item.is_section else "    ") + (item.name or ""))
        for attachment in item.attachments:
            client.download_attachment(attachment, Path(attachment.file_name or "file.pdf"))

    # Meeting-level documents (agenda PDF, packet, minutes)
    for file in event.published_files:
        client.download_file(file.file_id, Path(f"{file.file_id}.pdf"))
        text = client.get_file_text(file.file_id)  # best-effort, may be None
```

Every model keeps the raw API object in `.raw`, so fields the library
doesn't model yet are still reachable.

### Command line

The package installs a `muni` command that routes to a subcommand per
platform. `muni civicclerk demo exampletown` narrates a tour of the whole
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

Everything the library raises subclasses `CivicClerkError`:

- `UnknownTenantError` — the tenant subdomain doesn't exist (typo?)
- `NotFoundError` — an id-parameterized lookup (agenda, file) has no data
- `APIStatusError` — any other HTTP error status
- `NetworkError` — DNS/connection/timeout failures
- `PayloadError` — a response body the library can't use

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
prek run --all-files     # lint, format, type check (what CI enforces)

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
See [Acceptable use](docs/usage.md#acceptable-use) for details.

## License

MIT
