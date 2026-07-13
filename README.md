# libcivicclerk

A read-only Python client for the CivicClerk public meeting-portal API.

CivicClerk is a meeting-portal platform used by many municipalities to
publish meeting calendars, agendas, minutes, and supporting documents. Those
portals are backed by a public, unauthenticated API at
`https://{tenant}.api.civicclerk.com/v1`. This library gives developers a
small, typed, well-behaved client for reading that data — meeting calendars,
attendance details, structured agendas, and document downloads — without
reverse-engineering the API themselves.

## Install

```sh
pip install libcivicclerk
```

Requires Python 3.11+. The only runtime dependency is
[httpx](https://www.python-httpx.org/).

## Quickstart

The tenant name is the subdomain of a municipality's CivicClerk portal —
the `exampletown` in `exampletown.portal.civicclerk.com`.

```python
import datetime as dt
from pathlib import Path

from libcivicclerk import CivicClerkClient

with CivicClerkClient("exampletown") as client:
    # Boards and committees
    for category in client.get_event_categories():
        print(category.id, category.name)

    # This month's meetings for one board
    events = client.get_events(
        category_id=12,
        from_date=dt.date.today(),
        to_date=dt.date.today() + dt.timedelta(days=31),
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
```

## Disclaimer

This project is not affiliated with, endorsed by, or supported by CivicPlus
or the CivicClerk product. "CivicClerk" is used only to describe the API this
library talks to. The library reads publicly available government records;
please use it politely (modest request rates) and note that any
redistribution of downloaded documents is the responsibility of downstream
applications.

## License

MIT
