# API reference

## Client

Read-only client for one CivicClerk tenant's public API.

Parameters:

| Name                   | Type     | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Default                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tenant`               | `str`    | The tenant's subdomain — the exampletown in https://exampletown.api.civicclerk.com. Must be a single DNS label (letters, digits, and interior hyphens); it is interpolated into the API host and validated to that grammar, so a value containing a dot, slash, or other URL-significant character raises ValueError rather than silently addressing a different host.                                                                                                                                                                            | *required*                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `http_client`          | \`Client | None\`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Optional preconfigured httpx.Client (for timeouts, proxies, or transport injection in tests). When omitted, the client creates and owns one that follows redirects — attachment downloads are commonly served as a redirect to file storage, so an injected client should set follow_redirects=True as well. Either way, calling close (or using with) closes it. Unless the caller set a User-Agent header, it is replaced with the library's libmuni/{version} identifier. Do not attach ambient credentials (an Authorization header, an API key, cookies) to this client — see Security below. |
| `min_request_interval` | `float`  | Minimum seconds between requests — the client sleeps as needed so consecutive requests (including pagination and downloads) stay at least this far apart. Defaults to 1.0 (at most ~1 request/second) to stay polite toward small municipal servers and within a rate a human browsing the portal could produce; pass 0 to disable and own your request rate entirely. Pacing bounds the instantaneous rate only, not total volume — the portal operator's terms of use may also cap requests per day, which remains the caller's responsibility. | `1.0`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

Raises:

| Type         | Description                                |
| ------------ | ------------------------------------------ |
| `ValueError` | If tenant is not a single valid DNS label. |

Security

Attacker-influenced request targets. Attachment downloads follow `AgendaAttachment.download_url` verbatim, event pagination follows the response's absolute `@odata.nextLink`, and the library-owned client follows redirects for every request. A malicious or compromised tenant can therefore choose a host the client connects to — including internal or link-local addresses (server-side request forgery). Any header on the injected `http_client` is sent along, and `httpx` strips only `Authorization` on a cross-origin redirect, not custom headers or cookies. Do not put credentials on the injected client; when using untrusted tenants, isolate the network and consider an `http_client` with `follow_redirects=False`.

Exception diagnostics retain only a URL's scheme, host, port, and path. Userinfo, query strings, and fragments are omitted so signed attachment credentials and continuation tokens do not enter routine exception logs.

No response-size bounds. The client streams downloads to disk in chunks (large files never load fully into memory), but neither downloads nor JSON list responses are capped: a hostile or broken endpoint can exhaust disk (downloads) or memory (a listing page is parsed whole). Bounding response size is the caller's responsibility, alongside retries, caching, and rate limiting — enforce it in the injected `http_client` or around the call.

Example

> > > with CivicClerkClient("exampletown") as client: ... for category in client.get_event_categories(): ... print(category.id, category.name)

## get_event_categories

```
get_event_categories() -> list[EventCategory]
```

Fetch the tenant's meeting categories (boards and committees).

Returns:

| Type                  | Description                                        |
| --------------------- | -------------------------------------------------- |
| `list[EventCategory]` | All categories the tenant publishes, in API order. |

Raises:

| Type                 | Description                                |
| -------------------- | ------------------------------------------ |
| `UnknownTenantError` | If the tenant subdomain does not exist.    |
| `APIStatusError`     | If the API responds with an error status.  |
| `NetworkError`       | If the request fails at the network level. |
| `PayloadError`       | If the response body is not usable.        |

## iter_events

```
iter_events(
    *,
    category_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> Iterator[Event]
```

Iterate the tenant's meetings, oldest first, fetching lazily.

The API serves events in pages of 15; pages are fetched on demand (one HTTP request per page), so consuming only the first few events costs only the first request. Collect with `list(...)` when you need the complete result. With no filters that is the tenant's entire meeting history — potentially thousands of events and hundreds of requests — so pass a date range for anything interactive.

Parameters:

| Name          | Type   | Description | Default                                                                                                                                                 |
| ------------- | ------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `category_id` | \`int  | None\`      | Only events of this category (board/committee) — see get_event_categories.                                                                              |
| `from_date`   | \`date | None\`      | Only events on or after this date.                                                                                                                      |
| `to_date`     | \`date | None\`      | Only events on or before this date. Dates are interpreted on the tenant's local wall-clock timeline, matching the API's datetime semantics (see Event). |

Yields:

| Type    | Description                                       |
| ------- | ------------------------------------------------- |
| `Event` | Matching events, ordered by start time ascending. |

Raises:

| Type                 | Description                                |
| -------------------- | ------------------------------------------ |
| `UnknownTenantError` | If the tenant subdomain does not exist.    |
| `APIStatusError`     | If the API responds with an error status.  |
| `NetworkError`       | If the request fails at the network level. |
| `PayloadError`       | If a response body is not usable.          |

## get_agenda

```
get_agenda(agenda_id: int) -> Agenda
```

Fetch the structured agenda (sections, items, attachments) for a meeting.

Parameters:

| Name        | Type  | Description                                                                                     | Default    |
| ----------- | ----- | ----------------------------------------------------------------------------------------------- | ---------- |
| `agenda_id` | `int` | The agenda's id — see Event.agenda_id, which is None when an event has no published agenda yet. | *required* |

Returns:

| Type     | Description                                           |
| -------- | ----------------------------------------------------- |
| `Agenda` | The agenda's full item tree; use Agenda.walk_items to |
| `Agenda` | flatten it.                                           |

Raises:

| Type             | Description                                                                                                                                                                                |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `NotFoundError`  | If agenda_id does not exist. The API is inconsistent about how it signals this — sometimes a plain 404, sometimes a 200 with an empty/default payload — both are normalized to this error. |
| `APIStatusError` | If the API responds with another error status.                                                                                                                                             |
| `NetworkError`   | If the request fails at the network level.                                                                                                                                                 |
| `PayloadError`   | If the response body is not usable.                                                                                                                                                        |

## open_file

```
open_file(
    file_id: int,
) -> AbstractContextManager[FileStream]
```

Open a meeting-level file's response without writing it to disk.

Use this when the destination filename depends on the response: the yielded `FileStream` reports the file's content type, extension, and size before its body is read, so a caller can compose a name from `PublishedFile.name` (which has no extension) and the stream's `suffix`. Performs exactly one HTTP request, paced like any other.

The stream is only valid inside the `with` block; the response closes on exit. To download to a path you have already chosen, use `download_file` instead.

Parameters:

| Name      | Type  | Description                                                                             | Default    |
| --------- | ----- | --------------------------------------------------------------------------------------- | ---------- |
| `file_id` | `int` | A PublishedFile.file_id, as in download_file — never an AgendaAttachment.attachment_id. | *required* |

Returns:

| Type                                 | Description                                    |
| ------------------------------------ | ---------------------------------------------- |
| `AbstractContextManager[FileStream]` | A context manager yielding an open FileStream. |

Raises:

| Type             | Description                                                                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NotFoundError`  | If file_id does not exist. Raised on entering the with block, including for the API's "HTTP 200 with a 0-byte body" way of saying a file is unavailable. |
| `APIStatusError` | If the API responds with another error status.                                                                                                           |
| `NetworkError`   | If the request fails at the network level.                                                                                                               |

## open_attachment

```
open_attachment(
    attachment: AgendaAttachment,
) -> AbstractContextManager[FileStream]
```

Open an agenda attachment's response without writing it to disk.

The streaming counterpart to `download_attachment`, and the attachment counterpart to `open_file`: the yielded `FileStream` reports the attachment's content type, extension, and size before its body is read, so a caller can compose a name from `AgendaAttachment.file_name` (which has no extension) and the stream's `suffix`.

The bytes come from `attachment.download_url` — a signed, time-limited blob URL on a different host than the tenant API, requested with the same HTTP client. Expired URLs surface as `APIStatusError`.

Security

`download_url` is taken verbatim from the tenant's API response, so the tenant chooses the host this connects to (redirects included) — see the class `Security` note on server-side request forgery and injected-client credentials before fetching attachments from tenants you do not trust.

Parameters:

| Name         | Type               | Description                                       | Default    |
| ------------ | ------------------ | ------------------------------------------------- | ---------- |
| `attachment` | `AgendaAttachment` | The attachment to open; must have a download_url. | *required* |

Returns:

| Type                                 | Description                                               |
| ------------------------------------ | --------------------------------------------------------- |
| `AbstractContextManager[FileStream]` | A context manager yielding an open FileStream, valid only |
| `AbstractContextManager[FileStream]` | inside its with block.                                    |

Raises:

| Type             | Description                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ValueError`     | If attachment.download_url is None — link attachments and unpublished files have no file to stream. Raised immediately, not on entering the with block. |
| `NotFoundError`  | If the response body is empty, which the API also uses to mean "unavailable". Raised on entering the with block.                                        |
| `APIStatusError` | If the API responds with an error status (including an expired signed URL).                                                                             |
| `NetworkError`   | If the request fails at the network level.                                                                                                              |

## download_file

```
download_file(file_id: int, destination: Path) -> Path
```

Download a meeting-level file to `destination`.

Streams the response in chunks, so large files never load fully into memory. There is no existence-check endpoint (`HEAD` answers 405) and `Range` headers are ignored, so downloads cannot be resumed — a failed download must be retried from the start.

The one-liner for when you already know the name you want. When the name depends on the file's type, open the stream with `open_file` instead: it reports the content type, extension, and size before the body is read, and `destination` here is written verbatim.

Parameters:

| Name          | Type   | Description                                                                                                                                                                                                               | Default    |
| ------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `file_id`     | `int`  | A PublishedFile.file_id from Event.published_files. This id lives in a different namespace than AgendaAttachment.attachment_id — never pass an attachment id here; download attachments with download_attachment instead. | *required* |
| `destination` | `Path` | Local path to write the file to. Left untouched (no partial file) if the download fails.                                                                                                                                  | *required* |

Returns:

| Type   | Description                |
| ------ | -------------------------- |
| `Path` | destination, for chaining. |

Raises:

| Type             | Description                                                                                                                                               |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NotFoundError`  | If file_id does not exist. The API answers unknown ids with HTTP 200 and a 0-byte body rather than a 404, so an empty body is treated as "not found" too. |
| `APIStatusError` | If the API responds with another error status.                                                                                                            |
| `NetworkError`   | If the request fails at the network level.                                                                                                                |

## download_attachment

```
download_attachment(
    attachment: AgendaAttachment, destination: Path
) -> Path
```

Download an agenda attachment to `destination` via its signed URL.

Streams the response in chunks from `attachment.download_url` — a signed, time-limited blob URL on a different host than the tenant API, requested with the same injected HTTP client. Signed URLs expire; a request against an expired one surfaces as `APIStatusError`, not a distinct error type.

Security

`download_url` comes verbatim from the tenant's API response, so the tenant chooses the host this connects to (redirects included). See the class `Security` note on server-side request forgery, injected-client credentials, and the absence of a response-size cap before downloading from untrusted tenants.

The one-liner for when you already know the name you want. When the name depends on the file's type, open the stream with `open_attachment` instead; `destination` here is written verbatim.

Parameters:

| Name          | Type               | Description                                                                              | Default    |
| ------------- | ------------------ | ---------------------------------------------------------------------------------------- | ---------- |
| `attachment`  | `AgendaAttachment` | The attachment to download; must have a download_url.                                    | *required* |
| `destination` | `Path`             | Local path to write the file to. Left untouched (no partial file) if the download fails. | *required* |

Returns:

| Type   | Description                |
| ------ | -------------------------- |
| `Path` | destination, for chaining. |

Raises:

| Type             | Description                                                                                                                                             |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ValueError`     | If attachment.download_url is None — check it (and attachment.is_link) before calling; link attachments and unpublished files have no file to download. |
| `NotFoundError`  | If the response body is empty, which the API also uses to mean "unavailable".                                                                           |
| `APIStatusError` | If the API responds with an error status (including an expired signed URL).                                                                             |
| `NetworkError`   | If the request fails at the network level.                                                                                                              |

## get_file_text

```
get_file_text(file_id: int) -> str | None
```

Fetch the API's best-effort plain-text extraction of a file.

This is a best-effort upstream feature, not a guarantee: the API returns clean extracted text for some files, and an empty 200 response for others — including files that do have a text layer, and invalid ids — without distinguishing why. `None` means the API did not provide text; it does not mean the file lacks one.

Parameters:

| Name      | Type  | Description                                   | Default    |
| --------- | ----- | --------------------------------------------- | ---------- |
| `file_id` | `int` | A PublishedFile.file_id, as in download_file. | *required* |

Returns:

| Type  | Description |
| ----- | ----------- |
| \`str | None\`      |

Raises:

| Type             | Description                                    |
| ---------------- | ---------------------------------------------- |
| `NotFoundError`  | If file_id does not exist (a plain 404).       |
| `APIStatusError` | If the API responds with another error status. |
| `NetworkError`   | If the request fails at the network level.     |

## close

```
close() -> None
```

Close the underlying HTTP client.

## Models

All models are frozen dataclasses. Each keeps the unmodified API payload in its `raw` attribute, so upstream fields the library does not model yet stay reachable.

One meeting (past or upcoming) on a tenant's calendar.

Datetime semantics: the API stamps a `Z` (UTC) suffix on values that are actually local wall-clock times, so all datetimes on this model are naive and carry the wall-clock reading as published — an event at `19:00` local arrives as `19:00`, whatever the timezone.

## id

```
id: int
```

The event's stable numeric id.

## starts_at

```
starts_at: datetime
```

Scheduled start as a naive local wall-clock datetime.

## name

```
name: str | None = None
```

Event title.

## description

```
description: str | None = None
```

Event description, `None` when blank.

## category_id

```
category_id: int | None = None
```

Id of the event's category (board or committee).

## category_name

```
category_name: str | None = None
```

Name of the event's category.

## agenda_id

```
agenda_id: int | None = None
```

Key for the structured agenda, or `None` when no agenda is published (the API encodes that as `0`).

## agenda_name

```
agenda_name: str | None = None
```

Title of the published agenda.

## duration

```
duration: timedelta | None = None
```

Scheduled length, or `None` when the portal left it unset (the API encodes that as zero hours and minutes).

## location

```
location: EventLocation | None = None
```

Physical venue, or `None` when no address is given.

## virtual_meeting_url

```
virtual_meeting_url: str | None = None
```

Join link (Zoom, Teams, ...) when the portal publishes one.

## youtube_video_id

```
youtube_video_id: str | None = None
```

YouTube id of the meeting recording, if any.

## media_stream_url

```
media_stream_url: str | None = None
```

Direct stream URL of the recording, if any.

## published_files

```
published_files: list[PublishedFile] = field(
    default_factory=list
)
```

Meeting-level documents (agenda, packet, minutes, ...) published for this event.

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## recording_url

```
recording_url: str | None
```

A watchable URL for the meeting recording, if one exists.

Prefers the YouTube video when the portal uploaded one, falling back to the direct media stream; `None` when the event has no recording.

## from_api

```
from_api(raw: dict[str, Any]) -> Event
```

Build an `Event` from one `Events` response object.

Raises:

| Type           | Description                                                           |
| -------------- | --------------------------------------------------------------------- |
| `PayloadError` | If the load-bearing id or eventDate fields are absent or unparseable. |

A meeting category (board, commission, or committee) of a tenant.

## id

```
id: int
```

The category's stable numeric id, used to filter events.

## name

```
name: str | None = None
```

Human-readable category name (`None` if the API omits it).

## sort_order

```
sort_order: int | None = None
```

Position in the tenant's configured display order.

## is_public

```
is_public: bool | None = None
```

Whether the tenant marks the category public.

## parent_id

```
parent_id: int | None = None
```

Id of the parent category, or `None` for top-level categories (the API encodes "no parent" as `-1`).

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## from_api

```
from_api(raw: dict[str, Any]) -> EventCategory
```

Build an `EventCategory` from one API response object.

Parameters:

| Name  | Type             | Description                                            | Default    |
| ----- | ---------------- | ------------------------------------------------------ | ---------- |
| `raw` | `dict[str, Any]` | One entry of an EventCategories response's value list. | *required* |

Returns:

| Type            | Description                                  |
| --------------- | -------------------------------------------- |
| `EventCategory` | The parsed category, with raw kept verbatim. |

Raises:

| Type           | Description                             |
| -------------- | --------------------------------------- |
| `PayloadError` | If the load-bearing id field is absent. |

The physical address an event is held at.

All fields are best-effort; portals frequently use `address1` as a free-text room or venue description.

## address1

```
address1: str | None = None
```

First address line (often the venue or room).

## address2

```
address2: str | None = None
```

Second address line.

## city

```
city: str | None = None
```

City name.

## state

```
state: str | None = None
```

State or region.

## zip_code

```
zip_code: str | None = None
```

Postal code.

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## from_api

```
from_api(raw: dict[str, Any]) -> EventLocation | None
```

Build an `EventLocation`, or `None` when it is empty.

The API always includes an `eventLocation` object; when every address component is blank there is no usable location and this returns `None` so callers can simply test truthiness.

One meeting-level document published alongside an event.

## file_id

```
file_id: int
```

Stable numeric id, used to download the file.

## file_type

```
file_type: str | None = None
```

The portal's label for the document ("Agenda", "Agenda Packet", "Minutes", ...), or `None` if omitted.

## name

```
name: str | None = None
```

Human-readable file title.

## published_at

```
published_at: datetime | None = None
```

When the portal published the file, as a naive datetime (the API's timezone markers are unreliable; see `Event`).

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## from_api

```
from_api(raw: dict[str, Any]) -> PublishedFile
```

Build a `PublishedFile` from one `publishedFiles` entry.

Raises:

| Type           | Description                                 |
| -------------- | ------------------------------------------- |
| `PayloadError` | If the load-bearing fileId field is absent. |

The structured agenda (sections, items, attachments) for one meeting.

## agenda_id

```
agenda_id: int
```

The agenda's stable numeric id — matches `Event.agenda_id` (see that attribute for the `0`/"no agenda" sentinel, already normalized to `None` there).

## items

```
items: list[AgendaItem] = field(default_factory=list)
```

Top-level agenda nodes, ordered by `sort_order`. Use `walk_items` to flatten the whole tree.

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API response this model was parsed from.

## walk_items

```
walk_items() -> Iterator[AgendaItem]
```

Yield every item in the agenda tree, depth-first in sort order.

Each item is yielded before its children, and children are visited in `sort_order` before the next sibling — the same order the portal displays the agenda in — so callers can flatten the section/item tree into one ordered sequence without recursing themselves.

## from_api

```
from_api(raw: dict[str, Any]) -> Agenda
```

Build an `Agenda` from a `GET /Meetings/{agendaId}` response.

Raises:

| Type           | Description                             |
| -------------- | --------------------------------------- |
| `PayloadError` | If the load-bearing id field is absent. |

One node (section or item) in a structured agenda's tree.

## item_id

```
item_id: int
```

Stable numeric id of the agenda item.

## name

```
name: str | None = None
```

Item title.

## is_section

```
is_section: bool = False
```

Whether this node is a section heading rather than a substantive agenda item.

## sort_order

```
sort_order: int | None = None
```

Position of this item within the whole agenda's flat display order (shared across nesting levels).

## attachments

```
attachments: list[AgendaAttachment] = field(
    default_factory=list
)
```

Documents attached directly to this item.

## children

```
children: list[AgendaItem] = field(default_factory=list)
```

Nested items, ordered by `sort_order`.

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## from_api

```
from_api(raw: dict[str, Any]) -> AgendaItem
```

Build an `AgendaItem` from one `items`/`childItems` entry.

Raises:

| Type           | Description                             |
| -------------- | --------------------------------------- |
| `PayloadError` | If the load-bearing id field is absent. |

One document attached to a structured agenda item.

## attachment_id

```
attachment_id: int
```

Stable numeric id of the attachment. Note this id is reused in a different namespace by the file-download endpoint, so it must never be used to synthesize a download URL — use `download_url` instead.

## file_name

```
file_name: str | None = None
```

Human-readable title of the attachment.

## is_link

```
is_link: bool = False
```

Whether this attachment is a link rather than a downloadable file — link attachments have no `download_url`.

## download_url

```
download_url: str | None = None
```

Signed, time-limited URL to download the file directly, or `None` when absent (typically because the attachment is a link, or the portal has not published a file).

## raw

```
raw: dict[str, Any] = field(
    default_factory=dict, repr=False
)
```

The unmodified API object this model was parsed from.

## from_api

```
from_api(raw: dict[str, Any]) -> AgendaAttachment
```

Build an `AgendaAttachment` from one `attachmentsList` entry.

Raises:

| Type           | Description                             |
| -------------- | --------------------------------------- |
| `PayloadError` | If the load-bearing id field is absent. |

## Errors

Every operational error any libmuni client raises subclasses `MuniError`. The CivicClerk client's errors subclass `CivicClerkError`, which in turn subclasses `MuniError`, so a caller spanning platforms can catch them all at once. Two Python built-ins stay outside the hierarchy by design: `ValueError` for an invalid tenant or argument, and `OSError` for a failed local file write.

Bases: `Exception`

Base class for libmuni's operational errors (requests, parsing, downloads).

Bases: `MuniError`

Base class for every error the CivicClerk client raises.

Bases: `APIStatusError`

The tenant subdomain does not appear to exist.

The API returns an empty 404 both for unknown tenants and unknown paths; because this library only requests endpoints that exist on every tenant, a 404 on an always-present endpoint (such as `/EventCategories`) is interpreted as "no such tenant" — most often a typo in the tenant name.

Bases: `APIStatusError`

The id-parameterized resource does not exist for this tenant.

Raised by id-parameterized lookups (such as `CivicClerkClient.get_agenda`) when the requested id has no data — unlike `UnknownTenantError`, this says nothing about whether the tenant itself exists. The API is inconsistent about how it signals this: some invalid ids answer with a plain 404, while others answer 200 with an empty/default payload (`id` reset to `0`, no items) — both are surfaced as this error.

Bases: `CivicClerkError`

The API answered with an error status code.

Attributes:

| Name          | Type | Description                           |
| ------------- | ---- | ------------------------------------- |
| `status_code` |      | The HTTP status code of the response. |
| `url`         |      | The URL that was requested.           |

Bases: `CivicClerkError`

The request failed before a valid HTTP response arrived.

Covers DNS failures, refused connections, timeouts, and TLS problems. The originating `httpx.TransportError` is the `__cause__`.

Bases: `CivicClerkError`

The API responded successfully but the body was not usable.

Raised when a response is not valid JSON, or when a load-bearing field (an id or date the models cannot function without) is missing. Optional fields never raise this — they parse to `None`.
