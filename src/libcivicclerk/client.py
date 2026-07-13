"""The CivicClerk API client.

One client per tenant; every public method performs exactly one HTTP request
— except listings, where the API serves fixed pages of 15 and the client
follows continuation links (one request per page, stated in each docstring).
Results are typed models from :mod:`libcivicclerk.models`. The client adds
no caching, retries, or rate limiting — callers own their HTTP policy, and
can inject a configured :class:`httpx.Client` to apply it.
"""

import datetime as dt
import json
from collections.abc import Iterator
from typing import Any

import httpx

from libcivicclerk.errors import (
    APIStatusError,
    NetworkError,
    NotFoundError,
    PayloadError,
    UnknownTenantError,
)
from libcivicclerk.models import Agenda, Event, EventCategory


class CivicClerkClient:
    """Read-only client for one CivicClerk tenant's public API.

    Args:
        tenant: The tenant's subdomain — the ``exampletown`` in
            ``https://exampletown.api.civicclerk.com``.
        http_client: Optional preconfigured :class:`httpx.Client` (for
            timeouts, proxies, or transport injection in tests). When
            omitted, the client creates and owns one; either way, calling
            :meth:`close` (or using ``with``) closes it.

    Example:
        >>> with CivicClerkClient("exampletown") as client:
        ...     for category in client.get_event_categories():
        ...         print(category.id, category.name)
    """

    def __init__(self, tenant: str, *, http_client: httpx.Client | None = None) -> None:
        self.tenant = tenant
        self.base_url = f"https://{tenant}.api.civicclerk.com/v1"
        self._http = http_client if http_client is not None else httpx.Client()

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

    def get_events(
        self,
        *,
        category_id: int | None = None,
        from_date: dt.date | None = None,
        to_date: dt.date | None = None,
    ) -> list[Event]:
        """Fetch the tenant's meetings, oldest first.

        The API serves events in pages of 15; this method follows the
        continuation links and returns the complete result (one HTTP
        request per page). For lazy consumption of large ranges, use
        :meth:`iter_events`.

        Args:
            category_id: Only events of this category (board/committee) —
                see :meth:`get_event_categories`.
            from_date: Only events on or after this date.
            to_date: Only events on or before this date. Dates are
                interpreted on the tenant's local wall-clock timeline,
                matching the API's datetime semantics (see
                :class:`Event`).

        Returns:
            Matching events, ordered by start time ascending.

        Raises:
            UnknownTenantError: If the tenant subdomain does not exist.
            APIStatusError: If the API responds with an error status.
            NetworkError: If the request fails at the network level.
            PayloadError: If a response body is not usable.
        """
        return list(self.iter_events(category_id=category_id, from_date=from_date, to_date=to_date))

    def iter_events(
        self,
        *,
        category_id: int | None = None,
        from_date: dt.date | None = None,
        to_date: dt.date | None = None,
    ) -> Iterator[Event]:
        """Iterate the tenant's meetings, oldest first, fetching lazily.

        Same filters and errors as :meth:`get_events`; pages of 15 are
        fetched on demand, so consuming only the first few events costs
        only the first request.

        Yields:
            Matching events, ordered by start time ascending.
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
            agenda_id: The agenda's id — see :attr:`Event.agenda_id`, which
                is ``None`` when an event has no published agenda yet.

        Returns:
            The agenda's full item tree; use :meth:`Agenda.walk_items` to
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
                :meth:`_get_json_url`.
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

        Raises the library's typed errors. ``not_found_error`` controls how
        a 404 is interpreted: it defaults to :class:`UnknownTenantError`
        because most paths this client requests exist on every real tenant,
        so a 404 there means the tenant itself is missing. Callers making
        id-parameterized lookups (e.g. an agenda id that may simply not
        exist) pass a different error type — see
        :meth:`CivicClerkClient.get_agenda`.
        """
        try:
            response = self._http.get(url, params=params)
        except httpx.TransportError as exc:
            raise NetworkError(f"request to {url} failed: {exc}") from exc

        if response.status_code == 404:
            if issubclass(not_found_error, UnknownTenantError):
                raise not_found_error(
                    f"got 404 for {url}; tenant {self.tenant!r} likely does not exist",
                    status_code=404,
                    url=url,
                )
            raise not_found_error(f"got 404 for {url}", status_code=404, url=url)
        if response.is_error:
            raise APIStatusError(
                f"API returned {response.status_code} for {url}",
                status_code=response.status_code,
                url=url,
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise PayloadError(f"response from {url} is not valid JSON") from exc
