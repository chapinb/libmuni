"""Typed models for CivicClerk API responses.

Every model is a frozen dataclass built by a ``from_api`` classmethod and
keeps the raw response dict it was parsed from in ``raw``, so fields this
library does not model yet remain reachable.

Parsing is deliberately lenient: a small set of load-bearing fields (ids,
dates) must be present, while every other field falls back to ``None`` when
absent — the upstream API is undocumented and makes no compatibility
promises.
"""

import datetime as dt
import functools
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from libmuni.civicclerk.errors import PayloadError, require


def _guarded_parse(from_api):
    """Surface malformed field shapes as ``PayloadError``.

    Wraps a ``from_api`` classmethod so a field that is present but the
    wrong shape (a string id, a scalar where a list belongs) raises the
    library's typed error instead of leaking ``ValueError``/``TypeError``/
    ``AttributeError`` — keeping the promise that ``except CivicClerkError``
    catches anything a call can raise.
    """

    @functools.wraps(from_api)
    def parse(cls, raw):
        try:
            return from_api(cls, raw)
        except (AttributeError, TypeError, ValueError) as exc:
            raise PayloadError(f"{cls.__name__} payload is malformed: {exc}") from exc

    return parse


_SENTINEL_YEARS = (1, 1900)
"""Years the API uses as "no value" placeholders in datetime fields."""


def _text_or_none(value: Any) -> str | None:
    """Return ``value`` as text, mapping the API's empty strings to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _naive_datetime_or_none(value: Any) -> dt.datetime | None:
    """Parse an API datetime string to a naive ``datetime.datetime``.

    The API stamps a ``Z`` suffix on values that are actually local
    wall-clock times (evening meetings arrive as ``19:00:00Z``), so the
    suffix is stripped rather than trusted: callers get the wall-clock
    reading with ``tzinfo=None``. Sentinel dates (years 1 and 1900) and
    unparseable values become ``None``.
    """
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.year in _SENTINEL_YEARS:
        return None
    return parsed.replace(tzinfo=None)


@dataclass(frozen=True)
class EventCategory:
    """A meeting category (board, commission, or committee) of a tenant."""

    id: int
    """The category's stable numeric id, used to filter events."""

    name: str | None = None
    """Human-readable category name (``None`` if the API omits it)."""

    sort_order: int | None = None
    """Position in the tenant's configured display order."""

    is_public: bool | None = None
    """Whether the tenant marks the category public."""

    parent_id: int | None = None
    """Id of the parent category, or ``None`` for top-level categories
    (the API encodes "no parent" as ``-1``)."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "EventCategory":
        """Build an ``EventCategory`` from one API response object.

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
            name=_text_or_none(raw.get("categoryDesc")),
            sort_order=raw.get("sortOrder"),
            is_public=None if is_public is None else bool(is_public),
            parent_id=None if parent_id in (None, -1) else int(parent_id),
            raw=raw,
        )


@dataclass(frozen=True)
class PublishedFile:
    """One meeting-level document published alongside an event."""

    file_id: int
    """Stable numeric id, used to download the file."""

    file_type: str | None = None
    """The portal's label for the document ("Agenda", "Agenda Packet",
    "Minutes", ...), or ``None`` if omitted."""

    name: str | None = None
    """Human-readable file title."""

    published_at: dt.datetime | None = None
    """When the portal published the file, as a naive datetime (the API's
    timezone markers are unreliable; see ``Event``)."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "PublishedFile":
        """Build a ``PublishedFile`` from one ``publishedFiles`` entry.

        Raises:
            PayloadError: If the load-bearing ``fileId`` field is absent.
        """
        return cls(
            file_id=int(require(raw, "fileId", "PublishedFile")),
            file_type=_text_or_none(raw.get("type")),
            name=_text_or_none(raw.get("name")),
            published_at=_naive_datetime_or_none(raw.get("publishOn")),
            raw=raw,
        )


@dataclass(frozen=True)
class EventLocation:
    """The physical address an event is held at.

    All fields are best-effort; portals frequently use ``address1`` as a
    free-text room or venue description.
    """

    address1: str | None = None
    """First address line (often the venue or room)."""

    address2: str | None = None
    """Second address line."""

    city: str | None = None
    """City name."""

    state: str | None = None
    """State or region."""

    zip_code: str | None = None
    """Postal code."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "EventLocation | None":
        """Build an ``EventLocation``, or ``None`` when it is empty.

        The API always includes an ``eventLocation`` object; when every
        address component is blank there is no usable location and this
        returns ``None`` so callers can simply test truthiness.
        """
        location = cls(
            address1=_text_or_none(raw.get("address1")),
            address2=_text_or_none(raw.get("address2")),
            city=_text_or_none(raw.get("city")),
            state=_text_or_none(raw.get("state")),
            zip_code=_text_or_none(raw.get("zipCode")),
            raw=raw,
        )
        has_content = (
            location.address1
            or location.address2
            or location.city
            or location.state
            or location.zip_code
        )
        return location if has_content else None


@dataclass(frozen=True)
class Event:
    """One meeting (past or upcoming) on a tenant's calendar.

    Datetime semantics: the API stamps a ``Z`` (UTC) suffix on values that
    are actually local wall-clock times, so all datetimes on this model are
    naive and carry the wall-clock reading as published — an event at
    ``19:00`` local arrives as ``19:00``, whatever the timezone.
    """

    id: int
    """The event's stable numeric id."""

    starts_at: dt.datetime
    """Scheduled start as a naive local wall-clock datetime."""

    name: str | None = None
    """Event title."""

    description: str | None = None
    """Event description, ``None`` when blank."""

    category_id: int | None = None
    """Id of the event's category (board or committee)."""

    category_name: str | None = None
    """Name of the event's category."""

    agenda_id: int | None = None
    """Key for the structured agenda, or ``None`` when no agenda is
    published (the API encodes that as ``0``)."""

    agenda_name: str | None = None
    """Title of the published agenda."""

    duration: dt.timedelta | None = None
    """Scheduled length, or ``None`` when the portal left it unset (the
    API encodes that as zero hours and minutes)."""

    location: EventLocation | None = None
    """Physical venue, or ``None`` when no address is given."""

    virtual_meeting_url: str | None = None
    """Join link (Zoom, Teams, ...) when the portal publishes one."""

    youtube_video_id: str | None = None
    """YouTube id of the meeting recording, if any."""

    media_stream_url: str | None = None
    """Direct stream URL of the recording, if any."""

    published_files: list[PublishedFile] = field(default_factory=list)
    """Meeting-level documents (agenda, packet, minutes, ...) published
    for this event."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @property
    def recording_url(self) -> str | None:
        """A watchable URL for the meeting recording, if one exists.

        Prefers the YouTube video when the portal uploaded one, falling
        back to the direct media stream; ``None`` when the event has no
        recording.
        """
        if self.youtube_video_id:
            return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
        return self.media_stream_url

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "Event":
        """Build an ``Event`` from one ``Events`` response object.

        Raises:
            PayloadError: If the load-bearing ``id`` or ``eventDate``
                fields are absent or unparseable.
        """
        starts_at = _naive_datetime_or_none(require(raw, "eventDate", "Event"))
        if starts_at is None:
            raise PayloadError(f"Event {raw.get('id')} has unparseable eventDate")

        agenda_id = raw.get("agendaId")
        category_id = raw.get("categoryId")
        duration = dt.timedelta(
            hours=raw.get("durationHrs") or 0, minutes=raw.get("durationMin") or 0
        )
        return cls(
            id=int(require(raw, "id", "Event")),
            starts_at=starts_at,
            name=_text_or_none(raw.get("eventName")),
            description=_text_or_none(raw.get("eventDescription")),
            category_id=None if category_id is None else int(category_id),
            category_name=_text_or_none(raw.get("categoryName")),
            agenda_id=agenda_id if agenda_id else None,
            agenda_name=_text_or_none(raw.get("agendaName")),
            duration=duration or None,
            location=EventLocation.from_api(raw.get("eventLocation") or {}),
            virtual_meeting_url=_text_or_none(raw.get("externalMediaUrl")),
            youtube_video_id=_text_or_none(raw.get("youtubeVideoId")),
            media_stream_url=_text_or_none(raw.get("mediaStreamPath")),
            published_files=[
                PublishedFile.from_api(entry) for entry in (raw.get("publishedFiles") or [])
            ],
            raw=raw,
        )


def _sort_order_key(item: "AgendaItem") -> int:
    """Sort key placing items with no ``sortOrder`` first, stably."""
    return item.sort_order if item.sort_order is not None else 0


@dataclass(frozen=True)
class AgendaAttachment:
    """One document attached to a structured agenda item."""

    attachment_id: int
    """Stable numeric id of the attachment. Note this id is reused in a
    different namespace by the file-download endpoint, so it must never be
    used to synthesize a download URL — use ``download_url`` instead."""

    file_name: str | None = None
    """Human-readable title of the attachment."""

    is_link: bool = False
    """Whether this attachment is a link rather than a downloadable file —
    link attachments have no ``download_url``."""

    download_url: str | None = None
    """Signed, time-limited URL to download the file directly, or ``None``
    when absent (typically because the attachment is a link, or the portal
    has not published a file)."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "AgendaAttachment":
        """Build an ``AgendaAttachment`` from one ``attachmentsList`` entry.

        Raises:
            PayloadError: If the load-bearing ``id`` field is absent.
        """
        return cls(
            attachment_id=int(require(raw, "id", "AgendaAttachment")),
            file_name=_text_or_none(raw.get("fileName")),
            is_link=bool(raw.get("isLink")),
            download_url=_text_or_none(raw.get("pdfVersionFullPath")),
            raw=raw,
        )


@dataclass(frozen=True)
class AgendaItem:
    """One node (section or item) in a structured agenda's tree."""

    item_id: int
    """Stable numeric id of the agenda item."""

    name: str | None = None
    """Item title."""

    is_section: bool = False
    """Whether this node is a section heading rather than a substantive
    agenda item."""

    sort_order: int | None = None
    """Position of this item within the whole agenda's flat display order
    (shared across nesting levels)."""

    attachments: list[AgendaAttachment] = field(default_factory=list)
    """Documents attached directly to this item."""

    children: list["AgendaItem"] = field(default_factory=list)
    """Nested items, ordered by ``sort_order``."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API object this model was parsed from."""

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "AgendaItem":
        """Build an ``AgendaItem`` from one ``items``/``childItems`` entry.

        Raises:
            PayloadError: If the load-bearing ``id`` field is absent.
        """
        children = [AgendaItem.from_api(entry) for entry in (raw.get("childItems") or [])]
        children.sort(key=_sort_order_key)
        return cls(
            item_id=int(require(raw, "id", "AgendaItem")),
            name=_text_or_none(raw.get("agendaObjectItemName")),
            is_section=bool(raw.get("isSection")),
            sort_order=raw.get("sortOrder"),
            attachments=[
                AgendaAttachment.from_api(entry) for entry in (raw.get("attachmentsList") or [])
            ],
            children=children,
            raw=raw,
        )


@dataclass(frozen=True)
class Agenda:
    """The structured agenda (sections, items, attachments) for one meeting."""

    agenda_id: int
    """The agenda's stable numeric id — matches ``Event.agenda_id``
    (see that attribute for the ``0``/"no agenda" sentinel, already
    normalized to ``None`` there)."""

    items: list[AgendaItem] = field(default_factory=list)
    """Top-level agenda nodes, ordered by ``sort_order``. Use
    ``walk_items`` to flatten the whole tree."""

    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    """The unmodified API response this model was parsed from."""

    def walk_items(self) -> Iterator[AgendaItem]:
        """Yield every item in the agenda tree, depth-first in sort order.

        Each item is yielded before its children, and children are visited
        in ``sort_order`` before the next sibling — the same order the
        portal displays the agenda in — so callers can flatten the
        section/item tree into one ordered sequence without recursing
        themselves.
        """

        def _walk(items: list[AgendaItem]) -> Iterator[AgendaItem]:
            for item in items:
                yield item
                yield from _walk(item.children)

        yield from _walk(self.items)

    @classmethod
    @_guarded_parse
    def from_api(cls, raw: dict[str, Any]) -> "Agenda":
        """Build an ``Agenda`` from a ``GET /Meetings/{agendaId}`` response.

        Raises:
            PayloadError: If the load-bearing ``id`` field is absent.
        """
        items = [AgendaItem.from_api(entry) for entry in (raw.get("items") or [])]
        items.sort(key=_sort_order_key)
        return cls(
            agenda_id=int(require(raw, "id", "Agenda")),
            items=items,
            raw=raw,
        )
