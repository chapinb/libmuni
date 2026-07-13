"""Read-only Python client for the CivicClerk public meeting-portal API.

CivicClerk is a meeting-portal platform used by many municipalities to
publish meeting calendars, agendas, and documents. This library provides a
thin, typed client over the public (unauthenticated) API at
``https://{tenant}.api.civicclerk.com/v1``.
"""

from libcivicclerk.client import CivicClerkClient
from libcivicclerk.errors import (
    APIStatusError,
    CivicClerkError,
    NetworkError,
    NotFoundError,
    PayloadError,
    UnknownTenantError,
)
from libcivicclerk.models import (
    Agenda,
    AgendaAttachment,
    AgendaItem,
    Event,
    EventCategory,
    EventLocation,
    PublishedFile,
)

__version__ = "0.1.0"

__all__ = [
    "APIStatusError",
    "Agenda",
    "AgendaAttachment",
    "AgendaItem",
    "CivicClerkClient",
    "CivicClerkError",
    "Event",
    "EventCategory",
    "EventLocation",
    "NetworkError",
    "NotFoundError",
    "PayloadError",
    "PublishedFile",
    "UnknownTenantError",
    "__version__",
]
