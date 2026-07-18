"""Events slice: calendar data reaches the caller as typed Event models."""

import datetime as dt

import httpx
import pytest
from conftest import load_fixture, mock_client, recording_client

from libmuni.civicclerk import APIStatusError, Event, UnknownTenantError

# --- acceptance: the calendar story ---


def test_client_returns_typed_events():
    client = recording_client(load_fixture("events.json"), [])

    events = list(client.iter_events())

    assert [e.name for e in events] == [
        "Town Council Regular Meeting",
        "Planning Board Public Hearing",
        "Parks Subcommittee",
    ]
    assert events[0].id == 501
    assert events[0].category_name == "Town Council"


def test_event_start_is_naive_local_wall_clock_time():
    # The API stamps a Z suffix on what is actually local wall-clock time
    # (evening meetings arrive as 19:00:00Z), so the library must not claim
    # UTC: start is a naive datetime carrying the local reading.
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    assert events[0].starts_at == dt.datetime(2026, 8, 3, 19, 0)
    assert events[0].starts_at.tzinfo is None


# --- attendance story: location, virtual link, recording ---


def test_event_exposes_physical_location():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    location = events[0].location
    assert location is not None
    assert location.address1 == "Town Hall, Room 101"
    assert location.city == "Exampletown"

    assert events[2].location is None  # all address fields empty -> no location


def test_event_exposes_virtual_meeting_url():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    assert events[0].virtual_meeting_url == "https://exampletown-gov.zoom.us/j/1234567890"
    assert events[1].virtual_meeting_url is None  # empty string -> None


def test_event_exposes_duration_when_set():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    assert events[0].duration == dt.timedelta(hours=2, minutes=30)
    assert events[2].duration is None  # the API's 0h0m means "not set"


def test_event_exposes_recording_when_available():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    assert events[1].youtube_video_id == "dQw4w9WgXcQ"
    assert events[1].recording_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert events[0].recording_url is None


# --- materials story: published files and agenda linkage ---


def test_event_exposes_published_files():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    files = events[0].published_files
    assert [f.file_type for f in files] == ["Agenda", "Agenda Packet"]
    assert files[0].file_id == 9001
    assert files[0].published_at == dt.datetime(2026, 7, 30, 15, 12)
    assert events[2].published_files == []


def test_event_agenda_id_zero_means_no_agenda():
    events = list(recording_client(load_fixture("events.json"), []).iter_events())

    assert events[0].agenda_id == 7301
    assert events[2].agenda_id is None


# --- filtering: the request carries the caller's constraints ---


def test_iter_events_filters_by_category():
    seen: list[httpx.Request] = []
    list(recording_client({"value": []}, seen).iter_events(category_id=12))

    assert seen[0].url.params["$filter"] == "categoryId eq 12"


def test_iter_events_filters_by_date_range():
    seen: list[httpx.Request] = []
    list(
        recording_client({"value": []}, seen).iter_events(
            category_id=12,
            from_date=dt.date(2026, 7, 1),
            to_date=dt.date(2026, 8, 1),
        )
    )

    assert seen[0].url.params["$filter"] == (
        "categoryId eq 12"
        " and eventDate ge 2026-07-01T00:00:00Z"
        " and eventDate le 2026-08-01T23:59:59Z"
    )


# --- pagination: server pages are followed transparently ---


def paged_client(pages: list[dict], seen: list[str]):
    """Client serving ``pages`` in order, each page's nextLink wired to the next."""
    base = "https://exampletown.api.civicclerk.com/v1/Events"
    for index, page in enumerate(pages[:-1]):
        page["@odata.nextLink"] = f"{base}?$skiptoken=page-{index + 1}"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        token = request.url.params.get("$skiptoken")
        page_index = int(token.removeprefix("page-")) if token else 0
        return httpx.Response(200, json=pages[page_index])

    return mock_client(handler)


def event_stub(event_id: int) -> dict:
    return {"id": event_id, "eventDate": "2026-07-01T19:00:00Z"}


def test_iter_events_follows_next_links_to_completion():
    pages = [
        {"value": [event_stub(1), event_stub(2)]},
        {"value": [event_stub(3)]},
        {"value": [event_stub(4)]},
    ]
    seen: list[str] = []
    client = paged_client(pages, seen)

    events = list(client.iter_events())

    assert [e.id for e in events] == [1, 2, 3, 4]
    assert len(seen) == 3
    assert "$skiptoken=page-2" in seen[2]


def test_iter_events_reports_continuation_404_as_generic_api_error():
    base = "https://exampletown.api.civicclerk.com/v1/Events"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("$skiptoken"):
            return httpx.Response(404)
        page = {"value": [event_stub(1)], "@odata.nextLink": f"{base}?$skiptoken=page-1"}
        return httpx.Response(200, json=page)

    client = mock_client(handler)

    # Page 1 proved the tenant exists, so a later 404 is not an unknown tenant.
    with pytest.raises(APIStatusError) as exc_info:
        list(client.iter_events())
    assert not isinstance(exc_info.value, UnknownTenantError)


def test_iter_events_is_lazy_across_pages():
    pages = [
        {"value": [event_stub(1), event_stub(2)]},
        {"value": [event_stub(3)]},
    ]
    seen: list[str] = []
    client = paged_client(pages, seen)

    iterator = client.iter_events()
    first = next(iterator)

    assert first.id == 1
    assert len(seen) == 1  # the second page is not fetched until needed

    assert [e.id for e in iterator] == [2, 3]
    assert len(seen) == 2


# --- lenient parsing ---


def test_event_tolerates_minimal_payload():
    event = Event.from_api({"id": 1, "eventDate": "2026-01-05T19:00:00Z"})

    assert event.id == 1
    assert event.starts_at == dt.datetime(2026, 1, 5, 19, 0)
    assert event.name is None
    assert event.location is None
    assert event.published_files == []
    assert event.raw == {"id": 1, "eventDate": "2026-01-05T19:00:00Z"}
