"""The root of libmuni's operational errors.

Each vendor client defines its own error hierarchy, but all of them descend
from ``MuniError`` so a caller working across platforms can catch any of the
library's request, parse, and download failures with a single ``except``.
Vendor-specific bases (such as ``libmuni.civicclerk.CivicClerkError``) subclass
this and stay the right choice when a caller only touches one platform.

Two Python built-ins fall outside this hierarchy by design: ``ValueError`` for
an invalid tenant or argument (a programming error, caught at construction),
and ``OSError`` for a failed local file write. Neither describes the remote
service, so neither is wrapped.
"""


class MuniError(Exception):
    """Base class for libmuni's operational errors (requests, parsing, downloads)."""
