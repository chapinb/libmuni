# Usage guide

Everything here assumes the [quickstart](index.md) basics: one
`CivicClerkClient` per tenant, used as a context manager.

## Datetimes are local wall-clock time

The API stamps a `Z` (UTC) suffix on datetimes that are actually local
wall-clock times — a 7 pm meeting arrives as `19:00:00Z` whatever the
municipality's timezone — and nothing in the API declares the tenant's
timezone (verified against the OData schema and live tenants across five
US states). The library therefore returns **naive** datetimes carrying the
local reading.

If you need aware datetimes, attach the municipality's timezone yourself:

```python
from zoneinfo import ZoneInfo

local_tz = ZoneInfo("America/New_York")  # you know your municipality
aware = event.starts_at.replace(tzinfo=local_tz)
```

Date filters on `iter_events` are interpreted on the same local wall-clock
timeline, so "meetings this week" means the municipality's week — no
conversion needed.

## Request pacing, retries, and caching

The client is polite by default: consecutive requests (including
pagination pages and downloads) are spaced at least `min_request_interval`
seconds apart — 0.25 s out of the box, i.e. at most ~4 requests/second
against what are typically small municipal servers.

```python
client = CivicClerkClient("exampletown", min_request_interval=0)  # you own the rate
```

Retries and caching are deliberately **not** built in — they are policy
that varies per application. Configure them on an `httpx.Client` and
inject it:

```python
import httpx
from libcivicclerk import CivicClerkClient

http = httpx.Client(
    timeout=30.0,
    transport=httpx.HTTPTransport(retries=3),  # connect-level retries
)
client = CivicClerkClient("exampletown", http_client=http)
```

For response-level retries with backoff and a development cache, consider
wrapping your client with [careful](https://pypi.org/project/careful/) —
a library built for exactly this kind of polite scraping — and injecting
the result.

## Listing meetings

`iter_events` is lazy: the API serves pages of 15 and the client fetches
each page only when iteration reaches it. Collect with `list(...)` when
you want everything.

With **no filters it walks the tenant's entire meeting history** —
potentially thousands of events and hundreds of paged requests — so pass a
date range for anything interactive:

```python
import datetime as dt

recent = list(
    client.iter_events(
        from_date=dt.date.today() - dt.timedelta(days=30),
        to_date=dt.date.today(),
    )
)
```

## Downloads

Two id namespaces exist, and they must not be mixed:

- `PublishedFile.file_id` (meeting-level documents) → `download_file`
- `AgendaAttachment` (agenda-item documents) → `download_attachment`

An attachment id passed to `download_file` will not error cleanly — it
may download the wrong document. Always go through the matching method.

Practical limits inherited from the API:

- **No resume.** `Range` headers are ignored and `HEAD` is rejected, so a
  failed download restarts from zero. The library never leaves a partial
  file at the destination.
- **Empty 200 means unavailable.** The API answers unknown or unpublished
  files with an empty body and status 200; the library normalizes that to
  `NotFoundError`.
- **Attachment URLs expire.** `AgendaAttachment.download_url` is a
  signed, time-limited URL; an expired one surfaces as `APIStatusError`.
- `get_file_text` is best-effort upstream text extraction: `None` means
  the API returned no text, not that the document has none.

## Errors

Everything the library raises subclasses `CivicClerkError`:

| Error | Meaning |
| --- | --- |
| `UnknownTenantError` | The tenant subdomain doesn't exist (typo?) |
| `NotFoundError` | An id-parameterized lookup (agenda, file) has no data |
| `APIStatusError` | Any other HTTP error status |
| `NetworkError` | DNS, connection, or timeout failure |
| `PayloadError` | A response body the library can't use |

Absent optional data is never an error: an event with no published
materials has an empty `published_files`, not an exception. A blanket
`except CivicClerkError` catches everything the client can raise.

## Reaching unmodeled fields

Every model keeps its unmodified API payload in `.raw`. When the upstream
API grows a field the library doesn't model yet, it is already reachable:

```python
event.raw["secondaryIanaTimeZone"]  # anything the API sent
```
