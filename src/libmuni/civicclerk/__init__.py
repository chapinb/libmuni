"""Read-only Python client for the CivicClerk public meeting-portal API.

CivicClerk is a meeting-portal platform used by many municipalities to
publish meeting calendars, agendas, and documents. This package provides a
thin, typed client over the public (unauthenticated) API at
``https://{tenant}.api.civicclerk.com/v1``.
"""

from libmuni.civicclerk.client import CivicClerkClient
from libmuni.civicclerk.errors import (
    APIStatusError,
    CivicClerkError,
    NetworkError,
    NotFoundError,
    PayloadError,
    UnknownTenantError,
)
from libmuni.civicclerk.models import (
    Agenda,
    AgendaAttachment,
    AgendaItem,
    Event,
    EventCategory,
    EventLocation,
    PublishedFile,
)
from libmuni.civicclerk.streams import FileStream

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
    "FileStream",
    "NetworkError",
    "NotFoundError",
    "PayloadError",
    "PublishedFile",
    "UnknownTenantError",
]
