"""Typed models for CivicClerk API responses.

Every model is a frozen dataclass built by a ``from_api`` classmethod and
keeps the raw response dict it was parsed from in ``raw``, so fields this
library does not model yet remain reachable.

Parsing is deliberately lenient: a small set of load-bearing fields (ids,
dates) must be present, while every other field falls back to ``None`` when
absent — the upstream API is undocumented and makes no compatibility
promises.
"""

from dataclasses import dataclass, field
from typing import Any

from libcivicclerk.errors import require


@dataclass(frozen=True)
class EventCategory:
    """A meeting category (board, commission, or committee) of a tenant.

    Attributes:
        id: The category's stable numeric id, used to filter events.
        name: Human-readable category name (``None`` if the API omits it).
        sort_order: Position in the tenant's configured display order.
        is_public: Whether the tenant marks the category public.
        parent_id: Id of the parent category, or ``None`` for top-level
            categories (the API encodes "no parent" as ``-1``).
        raw: The unmodified API object this model was parsed from.
    """

    id: int
    name: str | None = None
    sort_order: int | None = None
    is_public: bool | None = None
    parent_id: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "EventCategory":
        """Build an :class:`EventCategory` from one API response object.

        Args:
            raw: One entry of an ``EventCategories`` response's ``value``
                list.

        Returns:
            The parsed category, with ``raw`` kept verbatim.

        Raises:
            PayloadError: If the load-bearing ``id`` field is absent.
        """
        parent_id = raw.get("parentId")
        is_public = raw.get("isPublic")
        return cls(
            id=int(require(raw, "id", "EventCategory")),
            name=raw.get("categoryDesc"),
            sort_order=raw.get("sortOrder"),
            is_public=None if is_public is None else bool(is_public),
            parent_id=None if parent_id in (None, -1) else int(parent_id),
            raw=raw,
        )
