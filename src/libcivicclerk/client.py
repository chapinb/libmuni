"""The CivicClerk API client.

One client per tenant; every public method performs exactly one HTTP request
— except listings, where the API serves fixed pages of 15 and the client
follows continuation links (one request per page, stated in each docstring).
Results are typed models from ``libcivicclerk.models``. The client
paces its requests politely by default (see ``min_request_interval``) but
adds no caching or retries — callers own that policy, and can inject a
configured ``httpx.Client`` to apply it.
"""

import datetime as dt
import json
import time
from collections.abc import Iterator
from importlib.metadata import version as _distribution_version
from pathlib import Path
from typing import Any

import httpx

from libcivicclerk.errors import (
    APIStatusError,
    NetworkError,
    NotFoundError,
    PayloadError,
    UnknownTenantError,
)
from libcivicclerk.models import Agenda, AgendaAttachment, Event, EventCategory

_USER_AGENT = (
    f"libcivicclerk/{_distribution_version('libcivicclerk')} "
    "(+https://github.com/chapinb/libcivicclerk)"
)
_HTTPX_DEFAULT_USER_AGENT = f"python-httpx/{httpx.__version__}"


class CivicClerkClient:
    """Read-only client for one CivicClerk tenant's public API.

    Args:
        tenant: The tenant's subdomain — the ``exampletown`` in
            ``https://exampletown.api.civicclerk.com``.
        http_client: Optional preconfigured ``httpx.Client`` (for
            timeouts, proxies, or transport injection in tests). When
            omitted, the client creates and owns one; either way, calling
            ``close`` (or using ``with``) closes it. Unless the
            caller set a ``User-Agent`` header, it is replaced with the
            library's ``libcivicclerk/{version}`` identifier.
        min_request_interval: Minimum seconds between requests — the
            client sleeps as needed so consecutive requests (including
            pagination and downloads) stay at least this far apart.
            Defaults to ``0.25`` (at most ~4 requests/second) to stay
            polite toward small municipal servers; pass ``0`` to disable
            and own your request rate entirely.

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
        min_request_interval: float = 0.25,
    ) -> None:
        self.tenant = tenant
        self.base_url = f"https://{tenant}.api.civicclerk.com/v1"
        self._min_interval = min_request_interval
        self._next_request_at = 0.0
        self._http = http_client if http_client is not None else httpx.Client()
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
            payload = self._get_json_url(next_link)

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

    def download_file(self, file_id: int, destination: Path) -> Path:
        """Download a meeting-level file to ``destination``.

        Streams the response in chunks, so large files never load fully
        into memory. There is no existence-check endpoint (``HEAD`` answers
        405) and ``Range`` headers are ignored, so downloads cannot be
        resumed — a failed download must be retried from the start.

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
        url = f"{self.base_url}/Meetings/GetMeetingFileStream(fileId={file_id},plainText=false)"
        return self._stream_to_file(url, destination, not_found_error=NotFoundError)

    def download_attachment(self, attachment: AgendaAttachment, destination: Path) -> Path:
        """Download an agenda attachment to ``destination`` via its signed URL.

        Streams the response in chunks from ``attachment.download_url`` — a
        signed, time-limited blob URL on a different host than the tenant
        API, requested with the same injected HTTP client. Signed URLs
        expire; a request against an expired one surfaces as
        ``APIStatusError``, not a distinct error type.

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
        if attachment.download_url is None:
            raise ValueError(
                f"attachment {attachment.attachment_id} has no download_url; "
                "check attachment.download_url is not None (and attachment.is_link "
                "is False) before calling download_attachment"
            )
        return self._stream_to_file(attachment.download_url, destination)

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
        (``_get`` and ``_stream_to_file``) call this first, so no
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
            return response.json()
        except json.JSONDecodeError as exc:
            raise PayloadError(f"response from {url} is not valid JSON") from exc

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
            raise NetworkError(f"request to {url} failed: {exc}") from exc
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
            message = f"got 404 for {url}"
            if issubclass(not_found_error, UnknownTenantError):
                message += f"; tenant {self.tenant!r} likely does not exist"
            raise not_found_error(message, status_code=404, url=url)
        if response.is_error:
            raise APIStatusError(
                f"API returned {response.status_code} for {url}",
                status_code=response.status_code,
                url=url,
            )

    def _stream_to_file(
        self,
        url: str,
        destination: Path,
        *,
        not_found_error: type[APIStatusError] = APIStatusError,
    ) -> Path:
        """Stream a GET response body to ``destination`` in chunks.

        Shared by ``download_file`` and ``download_attachment``.
        Guards against the API's "empty 200 means unavailable" behavior: no
        file is left at ``destination`` unless the download completed with
        a non-empty body.

        Args:
            url: Absolute URL to GET.
            destination: Local path to write the response body to.
            not_found_error: How to interpret a 404 — see
                ``_raise_for_error``.

        Returns:
            ``destination``.

        Raises:
            NotFoundError: If the response body is empty (the API's way of
                saying a file is unavailable), or on a 404 when
                ``not_found_error`` says so.
            APIStatusError: If the response is another error status.
            NetworkError: If the request fails at the network level.
        """
        self._pace()
        wrote_any_bytes = False
        opened_destination = False
        try:
            with self._http.stream("GET", url) as response:
                self._raise_for_error(response, url, not_found_error)
                opened_destination = True
                with destination.open("wb") as file:
                    for chunk in response.iter_bytes():
                        if chunk:
                            file.write(chunk)
                            wrote_any_bytes = True
            if not wrote_any_bytes:
                raise NotFoundError(
                    f"file at {url} is unavailable (empty response body)",
                    status_code=200,
                    url=url,
                )
        except httpx.TransportError as exc:
            if opened_destination:
                destination.unlink(missing_ok=True)
            raise NetworkError(f"request to {url} failed: {exc}") from exc
        except Exception:
            if opened_destination:
                destination.unlink(missing_ok=True)
            raise
        return destination
