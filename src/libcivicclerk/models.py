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
from dataclasses import dataclass, field
from typing import Any

from libcivicclerk.errors import PayloadError, require

_SENTINEL_YEARS = (1, 1900)
"""Years the API uses as "no value" placeholders in datetime fields."""


def _text_or_none(value: Any) -> str | None:
    """Return ``value`` as text, mapping the API's empty strings to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _naive_datetime_or_none(value: Any) -> dt.datetime | None:
    """Parse an API datetime string to a naive :class:`datetime.datetime`.

    The API stamps a ``Z`` suffix on values that are actually local
    wall-clock times (evening meetings arrive as ``19:00:00Z``), so the
    suffix is stripped rather than trusted: callers get the wall-clock
    reading with ``tzinfo=None``. Sentinel dates (years 1 and 1900) and
    unparseable values become ``None``.
    """
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.year in _SENTINEL_YEARS:
        return None
    return parsed.replace(tzinfo=None)


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


@dataclass(frozen=True)
class PublishedFile:
    """One meeting-level document published alongside an event.

    Attributes:
        file_id: Stable numeric id, used to download the file.
        file_type: The portal's label for the document ("Agenda",
            "Agenda Packet", "Minutes", ...), or ``None`` if omitted.
        name: Human-readable file title.
        published_at: When the portal published the file, as a naive
            datetime (the API's timezone markers are unreliable; see
            :class:`Event`).
        raw: The unmodified API object this model was parsed from.
    """

    file_id: int
    file_type: str | None = None
    name: str | None = None
    published_at: dt.datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "PublishedFile":
        """Build a :class:`PublishedFile` from one ``publishedFiles`` entry.

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

    Attributes:
        address1: First address line (often the venue or room).
        address2: Second address line.
        city: City name.
        state: State or region.
        zip_code: Postal code.
        raw: The unmodified API object this model was parsed from.
    """

    address1: str | None = None
    address2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "EventLocation | None":
        """Build an :class:`EventLocation`, or ``None`` when it is empty.

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

    Attributes:
        id: The event's stable numeric id.
        starts_at: Scheduled start as a naive local wall-clock datetime.
        name: Event title.
        description: Event description, ``None`` when blank.
        category_id: Id of the event's category (board or committee).
        category_name: Name of the event's category.
        agenda_id: Key for the structured agenda, or ``None`` when no
            agenda is published (the API encodes that as ``0``).
        agenda_name: Title of the published agenda.
        duration: Scheduled length, or ``None`` when the portal left it
            unset (the API encodes that as zero hours and minutes).
        location: Physical venue, or ``None`` when no address is given.
        virtual_meeting_url: Join link (Zoom, Teams, ...) when the portal
            publishes one.
        youtube_video_id: YouTube id of the meeting recording, if any.
        media_stream_url: Direct stream URL of the recording, if any.
        published_files: Meeting-level documents (agenda, packet,
            minutes, ...) published for this event.
        raw: The unmodified API object this model was parsed from.
    """

    id: int
    starts_at: dt.datetime
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    agenda_id: int | None = None
    agenda_name: str | None = None
    duration: dt.timedelta | None = None
    location: EventLocation | None = None
    virtual_meeting_url: str | None = None
    youtube_video_id: str | None = None
    media_stream_url: str | None = None
    published_files: list[PublishedFile] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

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
    def from_api(cls, raw: dict[str, Any]) -> "Event":
        """Build an :class:`Event` from one ``Events`` response object.

        Raises:
            PayloadError: If the load-bearing ``id`` or ``eventDate``
                fields are absent or unparseable.
        """
        starts_at = _naive_datetime_or_none(require(raw, "eventDate", "Event"))
        if starts_at is None:
            raise PayloadError(f"Event {raw.get('id')} has unparseable eventDate")

        agenda_id = raw.get("agendaId")
        category_id = raw.get("categoryId", raw.get("eventCategoryId"))
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
