"""Read-only Python client for the CivicClerk public meeting-portal API.

CivicClerk is a meeting-portal platform used by many municipalities to
publish meeting calendars, agendas, and documents. This library provides a
thin, typed client over the public (unauthenticated) API at
``https://{tenant}.api.civicclerk.com/v1``.
"""

from libcivicclerk.client import CivicClerkClient
from libcivicclerk.models import EventCategory

__version__ = "0.1.0"

__all__ = [
    "CivicClerkClient",
    "EventCategory",
    "__version__",
]
