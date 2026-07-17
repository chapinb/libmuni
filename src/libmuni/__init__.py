"""Read-only Python clients for municipal government software platforms.

A municipality's public record is spread across several vendor platforms, so
this library provides one thin, typed client per platform — currently
:mod:`libmuni.civicclerk` for meeting portals. The clients share no
cross-vendor domain model: what unifies them is the jurisdiction rather than a
schema. See ``docs/decisions.md``.
"""

from importlib.metadata import version as _distribution_version

__version__ = _distribution_version("libmuni")

__all__ = [
    "__version__",
]
