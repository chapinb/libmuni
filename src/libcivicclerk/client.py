"""The CivicClerk API client.

One client per tenant; every public method performs exactly one HTTP request
and returns typed models from :mod:`libcivicclerk.models`. The client adds
no caching, retries, or rate limiting — callers own their HTTP policy, and
can inject a configured :class:`httpx.Client` to apply it.
"""

import json
from typing import Any

import httpx

from libcivicclerk.errors import (
    APIStatusError,
    NetworkError,
    PayloadError,
    UnknownTenantError,
)
from libcivicclerk.models import EventCategory


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

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()

    def __enter__(self) -> "CivicClerkClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform one GET against the tenant API and return the JSON body.

        Raises the library's typed errors; a 404 is reported as
        :class:`UnknownTenantError` because every path this client requests
        exists on every real tenant (see that error's docstring).
        """
        url = f"{self.base_url}{path}"
        try:
            response = self._http.get(url, params=params)
        except httpx.TransportError as exc:
            raise NetworkError(f"request to {url} failed: {exc}") from exc

        if response.status_code == 404:
            raise UnknownTenantError(
                f"got 404 for {url}; tenant {self.tenant!r} likely does not exist",
                status_code=404,
                url=url,
            )
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
