"""The CivicClerk API client.

One client per tenant; every public method performs exactly one HTTP request
and returns typed models from :mod:`libcivicclerk.models`. The client adds
no caching, retries, or rate limiting — callers own their HTTP policy, and
can inject a configured :class:`httpx.Client` to apply it.
"""

from typing import Any

import httpx

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
            httpx.HTTPStatusError: If the API responds with an error status.
            httpx.TransportError: If the request fails at the network level.
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
        """Perform one GET against the tenant API and return the JSON body."""
        response = self._http.get(f"{self.base_url}{path}", params=params)
        response.raise_for_status()
        return response.json()
