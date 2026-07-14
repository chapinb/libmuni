# Cheat sheet

The whole library on one page: what exists, what will bite you, and what
does not exist at all. The [API reference](api.md) remains the authority on
exact signatures.

## The client

```python
from libcivicclerk import CivicClerkClient

with CivicClerkClient("exampletown") as client:  # the portal subdomain
    ...
```

`CivicClerkClient(tenant, *, http_client=None, min_request_interval=0.25)`.
Use it as a context manager, or call `close()` yourself. Each fetching method
below costs exactly one HTTP request — except `iter_events`, which spends one
per page it is asked for, and `close()`, which talks to nobody.

| Method | Purpose |
| --- | --- |
| `get_event_categories()` | The tenant's boards and committees. |
| `iter_events(*, category_id=None, from_date=None, to_date=None)` | Meetings, oldest first, fetched lazily one page at a time. |
| `get_agenda(agenda_id)` | One meeting's agenda tree. |
| `download_file(file_id, destination)` | Save a meeting-level document to a path you already know. |
| `download_attachment(attachment, destination)` | Save an agenda-item document. Takes the `AgendaAttachment`, not an id. |
| `open_file(file_id)` | Context manager yielding a `FileStream` — read the type before naming the file. |
| `open_attachment(attachment)` | The same, for an attachment's signed URL. `ValueError` if it has no `download_url`. |
| `get_file_text(file_id)` | Upstream's best-effort text extraction, or `None`. |
| `close()` | Release the HTTP connection pool. No request. |

The package also exports `__version__`, the installed library version.

## The stream

`FileStream` is what `open_file` and `open_attachment` yield, and the one
mutable, lifetime-bound object here: it wraps a live response and is valid
only inside its `with` block. Use it when the filename depends on the file's
type — the models' names (`PublishedFile.name`, `AgendaAttachment.file_name`)
carry no extension, and the response is the only place the extension lives.

| Member | Meaning |
| --- | --- |
| `content_type` | Media type, parameters stripped, e.g. `application/pdf`. `None` if unsent. |
| `suffix` | Extension with the leading dot, from `Content-Disposition`, else the content type, else the URL path. `None` when there is no basis — never a guessed `.pdf`. |
| `size` | `Content-Length` in bytes; `None` when the server streams chunked. |
| `iter_bytes()` | The body in chunks. Single pass, no disk. |
| `save(destination)` | Writes **exactly** `destination` and returns it — nothing appended or renamed. |

Opening a stream for an unavailable file raises `NotFoundError` from the
`with` statement itself, not partway through the body.

## The models

All are frozen dataclasses. Every one carries the unmodified API payload in
`.raw`, so a field the library does not model yet is still reachable.

Parsing is two-tier: the **load-bearing** field below is required, and a
payload missing it raises `PayloadError`. Everything else is best-effort and
arrives as `None` or an empty list rather than failing.

| Model | Load-bearing | Other fields |
| --- | --- | --- |
| `EventCategory` | `id` | `name`, `sort_order`, `is_public`, `parent_id` |
| `Event` | `id`, `starts_at` | `name`, `description`, `category_id`, `category_name`, `agenda_id`, `agenda_name`, `duration`, `location`, `virtual_meeting_url`, `youtube_video_id`, `media_stream_url`, `published_files` |
| `EventLocation` | — | `address1`, `address2`, `city`, `state`, `zip_code` |
| `PublishedFile` | `file_id` | `file_type`, `name`, `published_at` |
| `Agenda` | `agenda_id` | `items` |
| `AgendaItem` | `item_id` | `name`, `is_section`, `sort_order`, `attachments`, `children` |
| `AgendaAttachment` | `attachment_id` | `file_name`, `is_link`, `download_url` |

`AgendaItem.children` nests: an agenda is a tree, not a flat list.

## The errors

Everything raised subclasses `CivicClerkError`, so one `except` clause
catches the library whole.

| Error | Raised when |
| --- | --- |
| `UnknownTenantError` | The tenant subdomain does not exist. |
| `NotFoundError` | The API reports the id as missing. |
| `APIStatusError` | The API answered with an error status. |
| `NetworkError` | The request failed at the network level. |
| `PayloadError` | A response body was missing a load-bearing field. |

Absent optional data is never an error. A meeting with no documents has an
empty `published_files`, not an exception.

## Two traps

**Datetimes are naive local wall-clock time, not UTC.** The API stamps a `Z`
suffix on times that are really local: a 7 pm meeting arrives as
`19:00:00Z`, and nothing upstream declares the municipality's timezone. So
`event.starts_at` is a naive datetime carrying the local reading. Do not call
`.astimezone()` on it and do not treat it as UTC — attach the municipality's
timezone yourself with `replace(tzinfo=...)` if you need an aware value. Date
filters on `iter_events` run on that same local timeline.

**The two id namespaces are not interchangeable.** `PublishedFile.file_id`
goes to `download_file`; an `AgendaAttachment` goes to `download_attachment`.
The numbers overlap, so passing an attachment id to `download_file` usually
raises `NotFoundError` — but when that number also exists as a file id, it
silently downloads **the wrong document**. Always route through the matching
method.

## What this library does not have

These do not exist. If a snippet uses one, it is wrong.

- **No async client.** There is no `AsyncCivicClerkClient` and no
  `await`-able method. The client is synchronous, built on `httpx.Client`.
- **No writes.** No create, update, delete, subscribe, or comment. The
  upstream API surface used here is read-only.
- **No authentication.** No API key, token, or credential parameter — the
  portal data is public.
- **No search.** There is no full-text or keyword query method. Filtering is
  the three `iter_events` arguments and nothing more.
- **No retries, caching, or backoff.** Only `min_request_interval` pacing.
  Retries and caching are caller policy — inject a configured `httpx.Client`
  (built with `follow_redirects=True`; the client's own default does).
- **No timezone data.** The API does not publish one; see the first trap.
- **No resumable downloads.** Upstream ignores `Range` and rejects `HEAD`, so
  a failed download restarts from zero.
- **No pydantic.** Models are plain frozen dataclasses; `httpx` is the only
  runtime dependency.

## For LLMs and agents

The full documentation set is served as a single file:
[`llms-full.txt`](https://chapinb.github.io/libcivicclerk/latest/llms-full.txt).
An index in the [llms.txt](https://llmstxt.org/) format is at
[`llms.txt`](https://chapinb.github.io/libcivicclerk/latest/llms.txt).
