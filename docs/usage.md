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
from libmuni.civicclerk import CivicClerkClient

http = httpx.Client(
    timeout=30.0,
    transport=httpx.HTTPTransport(retries=3),  # connect-level retries
    follow_redirects=True,  # file streams may redirect to storage
)
client = CivicClerkClient("exampletown", http_client=http)
```

The client the library creates for you follows redirects already; an
injected client keeps httpx's default of *not* following them, so set
`follow_redirects=True` unless you have a reason not to.

Treat every API-provided request target as untrusted: attachment downloads use
the response's signed URL, event pagination follows its absolute continuation
URL, and enabled redirects apply to all requests. A malicious tenant can direct
those requests to internal services, carrying custom headers from an injected
client. Do not attach credentials to that client, and isolate its network when
using tenants you do not trust. See the packaged security policy for the full
threat model.

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

The namespaces overlap, so an attachment id passed to `download_file`
usually raises `NotFoundError` — but when the number happens to exist as a
file id too, it silently downloads the wrong document. Always go through
the matching method.

Practical limits inherited from the API:

- **No resume.** `Range` headers are ignored and `HEAD` is rejected, so a
  failed download restarts from zero. The library never leaves a partial
  file at the destination, and an existing destination remains unchanged.
- **Empty 200 means unavailable.** The API answers unknown or unpublished
  files with an empty body and status 200; the library normalizes that to
  `NotFoundError`.
- **Attachment URLs expire.** `AgendaAttachment.download_url` is a
  signed, time-limited URL; an expired one surfaces as `APIStatusError`.
- `get_file_text` is best-effort upstream text extraction: `None` means
  the API returned no text, not that the document has none.

## Naming a file you have not downloaded yet

`download_file` and `download_attachment` need a destination path before the
request goes out — but the only authoritative source for a file's type is the
response, and `HEAD` is rejected, so there is no way to ask ahead of time.
Hardcoding `.pdf` is right until the day a tenant publishes something else.

`open_file` and `open_attachment` hand you the response at the one moment the
information is actionable: after the headers arrive, before the body is read.
Both yield a `FileStream`, valid only inside the `with` block.

```python
for file in event.published_files:
    with client.open_file(file.file_id) as stream:
        # stream.content_type -> "application/pdf" (or None)
        # stream.size         -> bytes you will receive, or None if undeclared
        stream.save(downloads / f"{file.name}{stream.suffix or ''}")
```

The name is yours and the extension is the response's, and they meet inside
the block: `PublishedFile.name` and `AgendaAttachment.file_name` carry no
extension, and `stream.suffix` is derived from the response — the
`Content-Disposition` filename, else the content type, else the URL path. It
is `None` when the response gives no basis for one, rather than guessing.

`save(destination)` writes **exactly** the path you hand it: an extensionless
destination stays extensionless, and nothing is renamed or appended. It never
leaves a partial file behind.

To skip the disk entirely — streaming into a parser or an object store —
consume the bytes directly:

```python
with client.open_attachment(attachment) as stream:
    body = b"".join(stream.iter_bytes())  # or feed the chunks somewhere
```

The stream is single-pass and closes on exit; `iter_bytes` and `save` are
invalid afterward. An unavailable file (the empty-200 trap above) raises
`NotFoundError` from the `with` statement itself, so a caller that only
inspects the headers can never write a 0-byte file.

## Errors

Everything the library raises subclasses `CivicClerkError` — see the
[API reference](api.md#errors) for the full taxonomy and when each error
is raised.

Absent optional data is never an error: an event with no published
materials has an empty `published_files`, not an exception. A blanket
`except CivicClerkError` catches everything the client can raise.

The library deliberately emits no logs of its own. Typed exceptions provide
safe library-level diagnostics, with credentials removed from their URLs;
configure logging or event hooks on your injected `httpx.Client` when you need
request timing, retry, or wire-level observability. Ensure that application or
HTTP-client logging also redacts signed URLs, because models retain their full
download URLs for making requests.

## Reaching unmodeled fields

Every model keeps its unmodified API payload in `.raw`. When the upstream
API grows a field the library doesn't model yet, it is already reachable:

```python
event.raw["secondaryIanaTimeZone"]  # anything the API sent
```
