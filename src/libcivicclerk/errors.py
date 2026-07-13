"""Typed errors raised by this library.

Every error the library raises subclasses :class:`CivicClerkError`, so
``except CivicClerkError`` catches anything that can go wrong in a call.
Underlying :mod:`httpx` exceptions are attached as ``__cause__``.

Absent optional data is never an error: an event without materials yields
empty lists and ``None`` fields, not an exception.
"""

from typing import Any


class CivicClerkError(Exception):
    """Base class for every error this library raises."""


class NetworkError(CivicClerkError):
    """The request failed before a valid HTTP response arrived.

    Covers DNS failures, refused connections, timeouts, and TLS problems.
    The originating :class:`httpx.TransportError` is the ``__cause__``.
    """


class APIStatusError(CivicClerkError):
    """The API answered with an error status code.

    Attributes:
        status_code: The HTTP status code of the response.
        url: The URL that was requested.
    """

    def __init__(self, message: str, *, status_code: int, url: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url


class UnknownTenantError(APIStatusError):
    """The tenant subdomain does not appear to exist.

    The API returns an empty 404 both for unknown tenants and unknown
    paths; because this library only requests endpoints that exist on
    every tenant, a 404 on an always-present endpoint (such as
    ``/EventCategories``) is interpreted as "no such tenant" — most often
    a typo in the tenant name.
    """


class NotFoundError(APIStatusError):
    """The id-parameterized resource does not exist for this tenant.

    Raised by id-parameterized lookups (such as :meth:`CivicClerkClient.
    get_agenda`) when the requested id has no data — unlike
    :class:`UnknownTenantError`, this says nothing about whether the tenant
    itself exists. The API is inconsistent about how it signals this: some
    invalid ids answer with a plain 404, while others answer 200 with an
    empty/default payload (``id`` reset to ``0``, no items) — both are
    surfaced as this error.
    """


class PayloadError(CivicClerkError):
    """The API responded successfully but the body was not usable.

    Raised when a response is not valid JSON, or when a load-bearing
    field (an id or date the models cannot function without) is missing.
    Optional fields never raise this — they parse to ``None``.
    """


def require(raw: dict[str, Any], field_name: str, model_name: str) -> Any:
    """Return ``raw[field_name]``, raising :class:`PayloadError` if absent.

    Args:
        raw: The API response object being parsed.
        field_name: The load-bearing key that must be present and non-null.
        model_name: The model being built, for the error message.

    Returns:
        The field's value.

    Raises:
        PayloadError: If the field is missing or null.
    """
    value = raw.get(field_name)
    if value is None:
        raise PayloadError(
            f"{model_name} payload is missing load-bearing field {field_name!r}; "
            f"got keys {sorted(raw)}"
        )
    return value
