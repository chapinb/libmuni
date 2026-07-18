"""The CivicClerk API client.

One client per tenant; every public method performs exactly one HTTP request
— except listings, where the API serves fixed pages of 15 and the client
follows continuation links (one request per page, stated in each docstring).
Results are typed models from ``libmuni.civicclerk.models``. The client
paces its requests politely by default (see ``min_request_interval``) but
adds no caching or retries — callers own that policy, and can inject a
configured ``httpx.Client`` to apply it.
"""

import datetime as dt
import json
import re
import time
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from importlib.metadata import version as _distribution_version
from pathlib import Path
from typing import Any

import httpx

from libmuni.civicclerk.errors import (
    APIStatusError,
    NotFoundError,
    PayloadError,
    UnknownTenantError,
    _network_error,
    _safe_url,
)
from libmuni.civicclerk.models import Agenda, AgendaAttachment, Event, EventCategory
from libmuni.civicclerk.streams import FileStream

_USER_AGENT = f"libmuni/{_distribution_version('libmuni')} (+https://github.com/chapinb/libmuni)"
_HTTPX_DEFAULT_USER_AGENT = f"python-httpx/{httpx.__version__}"

_TENANT_PATTERN = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
"""A single DNS label: letters, digits, and interior hyphens, up to 63
characters. The tenant is interpolated into the API host, so it is validated
to that grammar — anything else (a dot, slash, ``@``, ``#``, or ``?``) could
redirect the request to a host other than ``{tenant}.api.civicclerk.com``."""


class CivicClerkClient:
    """Read-only client for one CivicClerk tenant's public API.

    Args:
        tenant: The tenant's subdomain — the ``exampletown`` in
            ``https://exampletown.api.civicclerk.com``. Must be a single
            DNS label (letters, digits, and interior hyphens); it is
            interpolated into the API host and validated to that grammar,
            so a value containing a dot, slash, or other URL-significant
            character raises ``ValueError`` rather than silently
            addressing a different host.
        http_client: Optional preconfigured ``httpx.Client`` (for
            timeouts, proxies, or transport injection in tests). When
            omitted, the client creates and owns one that follows
            redirects — attachment downloads are commonly served as a
            redirect to file storage, so an injected client should set
            ``follow_redirects=True`` as well. Either way, calling
            ``close`` (or using ``with``) closes it. Unless the
            caller set a ``User-Agent`` header, it is replaced with the
            library's ``libmuni/{version}`` identifier. Do not
            attach ambient credentials (an ``Authorization`` header, an
            API key, cookies) to this client — see Security below.
        min_request_interval: Minimum seconds between requests — the
            client sleeps as needed so consecutive requests (including
            pagination and downloads) stay at least this far apart.
            Defaults to ``1.0`` (at most ~1 request/second) to stay
            polite toward small municipal servers and within a rate a
            human browsing the portal could produce; pass ``0`` to
            disable and own your request rate entirely. Pacing bounds
            the instantaneous rate only, not total volume — the portal
            operator's terms of use may also cap requests per day, which
            remains the caller's responsibility.

    Raises:
        ValueError: If ``tenant`` is not a single valid DNS label.

    Security:
        Attacker-influenced request targets. Attachment downloads follow
        ``AgendaAttachment.download_url`` verbatim, event pagination follows
        the response's absolute ``@odata.nextLink``, and the library-owned
        client follows redirects for every request. A malicious or
        compromised tenant can therefore choose a host the client connects
        to — including internal or link-local addresses (server-side request
        forgery). Any header on the injected ``http_client`` is sent along,
        and ``httpx`` strips only ``Authorization`` on a cross-origin
        redirect, not custom headers or cookies. Do not put credentials on
        the injected client; when using untrusted tenants, isolate the
        network and consider an ``http_client`` with
        ``follow_redirects=False``.

        Exception diagnostics retain only a URL's scheme, host, port, and
        path. Userinfo, query strings, and fragments are omitted so signed
        attachment credentials and continuation tokens do not enter routine
        exception logs.

        No response-size bounds. The client streams downloads to disk in
        chunks (large files never load fully into memory), but neither
        downloads nor JSON list responses are capped: a hostile or broken
        endpoint can exhaust disk (downloads) or memory (a listing page is
        parsed whole). Bounding response size is the caller's
        responsibility, alongside retries, caching, and rate limiting —
        enforce it in the injected ``http_client`` or around the call.

    Example:
        >>> with CivicClerkClient("exampletown") as client:
        ...     for category in client.get_event_categories():
        ...         print(category.id, category.name)
    """

    def __init__(
        self,
        tenant: str,
        *,
        http_client: httpx.Client | None = None,
        min_request_interval: float = 1.0,
    ) -> None:
        if not _TENANT_PATTERN.match(tenant):
            raise ValueError(
                f"invalid tenant {tenant!r}: expected a single subdomain label "
                "(letters, digits, and interior hyphens, up to 63 characters), "
                "as in 'exampletown' — not a URL, dotted host, or path"
            )
        self.tenant = tenant
        self.base_url = f"https://{tenant}.api.civicclerk.com/v1"
        self._min_interval = min_request_interval
        self._next_request_at = 0.0
        self._http = http_client if http_client is not None else httpx.Client(follow_redirects=True)
        if self._http.headers.get("user-agent") in ("", _HTTPX_DEFAULT_USER_AGENT):
            self._http.headers["user-agent"] = _USER_AGENT

    def get_event_categories(self) -> list[EventCategory]:
        """Fetch the tenant's meeting categories (boards and committees).

        Returns:
            All categories the tenant publishes, in API order.

        Raises:
            UnknownTenantError: If the tenant subdomain does not exist.
            APIStatusError: If the API responds with an error status.
            NetworkError: If the request fails at the network level.
            PayloadError: If the response body is not usable.
        """
        payload = self._get_json("/EventCategories")
        return [EventCategory.from_api(entry) for entry in payload.get("value", [])]

    def iter_events(
        self,
        *,
        category_id: int | None = None,
        from_date: dt.date | None = None,
        to_date: dt.date | None = None,
    ) -> Iterator[Event]:
        """Iterate the tenant's meetings, oldest first, fetching lazily.

        The API serves events in pages of 15; pages are fetched on demand
        (one HTTP request per page), so consuming only the first few
        events costs only the first request. Collect with ``list(...)``
        when you need the complete result. With no filters that is the
        tenant's entire meeting history — potentially thousands of events
        and hundreds of requests — so pass a date range for anything
        interactive.

        Args:
            category_id: Only events of this category (board/committee) —
                see ``get_event_categories``.
            from_date: Only events on or after this date.
            to_date: Only events on or before this date. Dates are
                interpreted on the tenant's local wall-clock timeline,
                matching the API's datetime semantics (see
                ``Event``).

        Yields:
            Matching events, ordered by start time ascending.

        Raises:
            UnknownTenantError: If the tenant subdomain does not exist.
            APIStatusError: If the API responds with an error status.
            NetworkError: If the request fails at the network level.
            PayloadError: If a response body is not usable.
        """
        filters = []
        if category_id is not None:
            filters.append(f"categoryId eq {category_id}")
        if from_date is not None:
            filters.append(f"eventDate ge {from_date.isoformat()}T00:00:00Z")
        if to_date is not None:
            filters.append(f"eventDate le {to_date.isoformat()}T23:59:59Z")

        params: dict[str, Any] = {"$orderby": "eventDate asc"}
        if filters:
            params["$filter"] = " and ".join(filters)

        payload = self._get_json("/Events", params=params)
        while True:
            for entry in payload.get("value", []):
                yield Event.from_api(entry)
            next_link = payload.get("@odata.nextLink")
            if not next_link:
                return
            # Page 1 already proved the tenant exists, so a 404 on a
            # continuation link is a generic API error, not an unknown tenant.
            payload = self._get_json_url(next_link, not_found_error=APIStatusError)

    def get_agenda(self, agenda_id: int) -> Agenda:
        """Fetch the structured agenda (sections, items, attachments) for a meeting.

        Args:
            agenda_id: The agenda's id — see ``Event.agenda_id``, which
                is ``None`` when an event has no published agenda yet.

        Returns:
            The agenda's full item tree; use ``Agenda.walk_items`` to
            flatten it.

        Raises:
            NotFoundError: If ``agenda_id`` does not exist. The API is
                inconsistent about how it signals this — sometimes a plain
                404, sometimes a 200 with an empty/default payload — both
                are normalized to this error.
            APIStatusError: If the API responds with another error status.
            NetworkError: If the request fails at the network level.
            PayloadError: If the response body is not usable.
        """
        payload = self._get_json(f"/Meetings/{agenda_id}", not_found_error=NotFoundError)
        if not payload.get("id"):
            raise NotFoundError(
                f"no agenda with id {agenda_id} for tenant {self.tenant!r}",
                status_code=200,
                url=f"{self.base_url}/Meetings/{agenda_id}",
            )
        return Agenda.from_api(payload)

    def open_file(self, file_id: int) -> AbstractContextManager[FileStream]:
        """Open a meeting-level file's response without writing it to disk.

        Use this when the destination filename depends on the response: the
        yielded ``FileStream`` reports the file's content type, extension,
        and size before its body is read, so a caller can compose a name
        from ``PublishedFile.name`` (which has no extension) and the
        stream's ``suffix``. Performs exactly one HTTP request, paced like
        any other.

        The stream is only valid inside the ``with`` block; the response
        closes on exit. To download to a path you have already chosen, use
        ``download_file`` instead.

        Args:
            file_id: A ``PublishedFile.file_id``, as in ``download_file`` —
                never an ``AgendaAttachment.attachment_id``.

        Returns:
            A context manager yielding an open ``FileStream``.

        Raises:
            NotFoundError: If ``file_id`` does not exist. Raised on entering
                the ``with`` block, including for the API's "HTTP 200 with a
                0-byte body" way of saying a file is unavailable.
            APIStatusError: If the API responds with another error status.
            NetworkError: If the request fails at the network level.
        """
        url = f"{self.base_url}/Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"
        return self._open_stream(url, not_found_error=NotFoundError)

    def open_attachment(self, attachment: AgendaAttachment) -> AbstractContextManager[FileStream]:
        """Open an agenda attachment's response without writing it to disk.

        The streaming counterpart to ``download_attachment``, and the
        attachment counterpart to ``open_file``: the yielded ``FileStream``
        reports the attachment's content type, extension, and size before
        its body is read, so a caller can compose a name from
        ``AgendaAttachment.file_name`` (which has no extension) and the
        stream's ``suffix``.

        The bytes come from ``attachment.download_url`` — a signed,
        time-limited blob URL on a different host than the tenant API,
        requested with the same HTTP client. Expired URLs surface as
        ``APIStatusError``.

        Security:
            ``download_url`` is taken verbatim from the tenant's API
            response, so the tenant chooses the host this connects to
            (redirects included) — see the class ``Security`` note on
            server-side request forgery and injected-client credentials
            before fetching attachments from tenants you do not trust.

        Args:
            attachment: The attachment to open; must have a
                ``download_url``.

        Returns:
            A context manager yielding an open ``FileStream``, valid only
            inside its ``with`` block.

        Raises:
            ValueError: If ``attachment.download_url`` is ``None`` — link
                attachments and unpublished files have no file to stream.
                Raised immediately, not on entering the ``with`` block.
            NotFoundError: If the response body is empty, which the API
                also uses to mean "unavailable". Raised on entering the
                ``with`` block.
            APIStatusError: If the API responds with an error status
                (including an expired signed URL).
            NetworkError: If the request fails at the network level.
        """
        if attachment.download_url is None:
            raise ValueError(
                f"attachment {attachment.attachment_id} has no download_url; "
                "check attachment.download_url is not None (and attachment.is_link "
                "is False) before calling download_attachment"
            )
        return self._open_stream(attachment.download_url)

    @contextmanager
    def _open_stream(
        self,
        url: str,
        *,
        not_found_error: type[APIStatusError] = APIStatusError,
    ) -> Iterator[FileStream]:
        """Stream a GET response, yielding it as a ``FileStream``.

        The request funnel for every download path: paces the request,
        translates failures that happen *before* the response exists
        (connect, TLS, timeout) into this library's typed errors, and closes
        the response on exit. Once the response exists, reading its body —
        and translating a failure partway through it — belongs to
        ``FileStream``, which owns the bytes.

        Args:
            url: Absolute URL to GET.
            not_found_error: How to interpret a 404 — see
                ``_raise_for_error``.
        """
        self._pace()
        try:
            with self._http.stream("GET", url) as response:
                self._raise_for_error(response, url, not_found_error)
                yield FileStream(response)
        except httpx.TransportError as exc:
            raise _network_error(url, exc) from exc

    def download_file(self, file_id: int, destination: Path) -> Path:
        """Download a meeting-level file to ``destination``.

        Streams the response in chunks, so large files never load fully
        into memory. There is no existence-check endpoint (``HEAD`` answers
        405) and ``Range`` headers are ignored, so downloads cannot be
        resumed — a failed download must be retried from the start.

        The one-liner for when you already know the name you want. When the
        name depends on the file's type, open the stream with ``open_file``
        instead: it reports the content type, extension, and size before the
        body is read, and ``destination`` here is written verbatim.

        Args:
            file_id: A ``PublishedFile.file_id`` from
                ``Event.published_files``. This id lives in a different
                namespace than ``AgendaAttachment.attachment_id`` —
                never pass an attachment id here; download attachments with
                ``download_attachment`` instead.
            destination: Local path to write the file to. Left untouched
                (no partial file) if the download fails.

        Returns:
            ``destination``, for chaining.

        Raises:
            NotFoundError: If ``file_id`` does not exist. The API answers
                unknown ids with HTTP 200 and a 0-byte body rather than a
                404, so an empty body is treated as "not found" too.
            APIStatusError: If the API responds with another error status.
            NetworkError: If the request fails at the network level.
        """
        with self.open_file(file_id) as stream:
            return stream.save(destination)

    def download_attachment(self, attachment: AgendaAttachment, destination: Path) -> Path:
        """Download an agenda attachment to ``destination`` via its signed URL.

        Streams the response in chunks from ``attachment.download_url`` — a
        signed, time-limited blob URL on a different host than the tenant
        API, requested with the same injected HTTP client. Signed URLs
        expire; a request against an expired one surfaces as
        ``APIStatusError``, not a distinct error type.

        Security:
            ``download_url`` comes verbatim from the tenant's API response,
            so the tenant chooses the host this connects to (redirects
            included). See the class ``Security`` note on server-side
            request forgery, injected-client credentials, and the absence
            of a response-size cap before downloading from untrusted
            tenants.

        The one-liner for when you already know the name you want. When the
        name depends on the file's type, open the stream with
        ``open_attachment`` instead; ``destination`` here is written
        verbatim.

        Args:
            attachment: The attachment to download; must have a
                ``download_url``.
            destination: Local path to write the file to. Left untouched
                (no partial file) if the download fails.

        Returns:
            ``destination``, for chaining.

        Raises:
            ValueError: If ``attachment.download_url`` is ``None`` — check
                it (and ``attachment.is_link``) before calling; link
                attachments and unpublished files have no file to download.
            NotFoundError: If the response body is empty, which the API
                also uses to mean "unavailable".
            APIStatusError: If the API responds with an error status
                (including an expired signed URL).
            NetworkError: If the request fails at the network level.
        """
        with self.open_attachment(attachment) as stream:
            return stream.save(destination)

    def get_file_text(self, file_id: int) -> str | None:
        """Fetch the API's best-effort plain-text extraction of a file.

        This is a best-effort upstream feature, not a guarantee: the API
        returns clean extracted text for some files, and an empty 200
        response for others — including files that do have a text layer,
        and invalid ids — without distinguishing why. ``None`` means the
        API did not provide text; it does not mean the file lacks one.

        Args:
            file_id: A ``PublishedFile.file_id``, as in
                ``download_file``.

        Returns:
            The extracted text, or ``None`` if the API returned no text.

        Raises:
            NotFoundError: If ``file_id`` does not exist (a plain 404).
            APIStatusError: If the API responds with another error status.
            NetworkError: If the request fails at the network level.
        """
        url = f"{self.base_url}/Meetings/GetMeetingFileStream(fileId={file_id},plainText=true)"
        response = self._get(url, not_found_error=NotFoundError)
        return response.text or None

    def _pace(self) -> None:
        """Sleep until ``min_request_interval`` has elapsed since the last request.

        The polite-by-default request gate: both request funnels
        (``_get`` and ``_open_stream``) call this first, so no
        two requests start closer together than the configured interval.
        Blocks the calling thread; a zero (or negative) interval disables
        pacing entirely.
        """
        if self._min_interval <= 0:
            return
        delay = self._next_request_at - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        self._next_request_at = time.monotonic() + self._min_interval

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> "CivicClerkClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        not_found_error: type[APIStatusError] = UnknownTenantError,
    ) -> dict[str, Any]:
        """Perform one GET against the tenant API and return the JSON body.

        Args:
            path: Path under the tenant's base URL.
            params: Optional query parameters.
            not_found_error: Error type to raise on a 404 response — see
                ``_get_json_url``.
        """
        return self._get_json_url(
            f"{self.base_url}{path}", params=params, not_found_error=not_found_error
        )

    def _get_json_url(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        not_found_error: type[APIStatusError] = UnknownTenantError,
    ) -> dict[str, Any]:
        """GET an absolute URL (e.g. a continuation link) as JSON.

        Raises the library's typed errors — see ``_raise_for_error``.
        """
        response = self._get(url, params=params, not_found_error=not_found_error)
        try:
            payload = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise PayloadError(f"response from {_safe_url(url)} is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise PayloadError(
                f"response from {_safe_url(url)} must be a JSON object, "
                f"got {type(payload).__name__}"
            )
        value = payload.get("value", [])
        if not isinstance(value, list):
            raise PayloadError(
                f"response from {_safe_url(url)} field 'value' must be an array, "
                f"got {type(value).__name__}"
            )
        return payload

    def _get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        not_found_error: type[APIStatusError],
    ) -> httpx.Response:
        """GET ``url``, translating failures into this library's errors."""
        self._pace()
        try:
            response = self._http.get(url, params=params)
        except httpx.TransportError as exc:
            raise _network_error(url, exc) from exc
        self._raise_for_error(response, url, not_found_error)
        return response

    def _raise_for_error(
        self,
        response: httpx.Response,
        url: str,
        not_found_error: type[APIStatusError],
    ) -> None:
        """Translate an error response into this library's typed errors.

        The single place that encodes how the API signals failure.
        ``not_found_error`` controls how a 404 is interpreted: most paths
        this client requests exist on every real tenant, so a 404 there
        means the tenant itself is missing (``UnknownTenantError``);
        id-parameterized lookups pass ``NotFoundError`` instead, and
        requests to non-tenant hosts (signed blob URLs) pass plain
        ``APIStatusError``.
        """
        if response.status_code == 404:
            message = f"got 404 for {_safe_url(url)}"
            if issubclass(not_found_error, UnknownTenantError):
                message += f"; tenant {self.tenant!r} likely does not exist"
            raise not_found_error(message, status_code=404, url=url)
        if response.is_error:
            raise APIStatusError(
                f"API returned {response.status_code} for {_safe_url(url)}",
                status_code=response.status_code,
                url=url,
            )
