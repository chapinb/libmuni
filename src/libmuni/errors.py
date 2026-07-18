"""The root of every error libmuni raises.

Each vendor client defines its own error hierarchy, but all of them descend
from ``MuniError`` so a caller working across platforms can catch any of the
library's failures with a single ``except``. Vendor-specific bases (such as
``libmuni.civicclerk.CivicClerkError``) subclass this and stay the right
choice when a caller only touches one platform.
"""


class MuniError(Exception):
    """Base class for every error raised by any libmuni client."""
