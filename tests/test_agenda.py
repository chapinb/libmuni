"""Agenda structure slice: sections/items/attachments reach the caller as a
typed tree, and unknown agenda ids are distinguished from unknown tenants.
"""

import httpx
import pytest
from conftest import load_fixture, mock_client, recording_client

from libmuni.civicclerk import Agenda, CivicClerkClient, NotFoundError
from libmuni.civicclerk.models import AgendaItem


def status_client(status_code: int, payload: dict | None = None) -> CivicClerkClient:
    """Client whose transport always answers with a fixed status code."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload if payload is not None else {})

    return mock_client(handler)


# --- acceptance: browsing the structured agenda tree ---


def test_get_agenda_returns_typed_tree():
    client = recording_client(load_fixture("agenda.json"), [])

    agenda = client.get_agenda(7301)

    assert agenda.agenda_id == 7301
    assert [item.name for item in agenda.items] == [
        "CALL TO ORDER",
        "APPROVAL OF MINUTES",
        "NEW BUSINESS",
        "ADJOURNMENT",
    ]
    assert agenda.items[0].is_section is True


def test_get_agenda_requests_path_style_meetings_endpoint():
    seen: list[httpx.Request] = []
    recording_client(load_fixture("agenda.json"), seen).get_agenda(7301)

    assert str(seen[0].url) == "https://exampletown.api.civicclerk.com/v1/Meetings/7301"


def test_agenda_item_exposes_children_and_attachments():
    agenda = recording_client(load_fixture("agenda.json"), []).get_agenda(7301)

    minutes_section = agenda.items[1]
    assert minutes_section.name == "APPROVAL OF MINUTES"
    assert len(minutes_section.children) == 1

    minutes_item = minutes_section.children[0]
    assert minutes_item.is_section is False
    assert len(minutes_item.attachments) == 1
    assert minutes_item.attachments[0].file_name == "June 2026 Minutes"
    assert minutes_item.attachments[0].download_url == (
        "https://exampletown.blob.core.windows.net/stream/exampletown/"
        "minutes-june-2026.pdf?sig=abc123"
    )


def test_agenda_item_with_no_attachments():
    agenda = recording_client(load_fixture("agenda.json"), []).get_agenda(7301)

    discussion_item = agenda.items[2].children[1]
    assert discussion_item.name == "Discussion: parking study"
    assert discussion_item.attachments == []


def test_link_attachment_has_no_download_url():
    agenda = recording_client(load_fixture("agenda.json"), []).get_agenda(7301)

    resolution_item = agenda.items[2].children[0]
    link_attachment = resolution_item.attachments[1]

    assert link_attachment.file_name == "Related news article"
    assert link_attachment.is_link is True
    assert link_attachment.download_url is None


# --- walk order: depth-first flattening for callers ---


def test_walk_items_is_depth_first_in_sort_order():
    agenda = recording_client(load_fixture("agenda.json"), []).get_agenda(7301)

    assert [item.name for item in agenda.walk_items()] == [
        "CALL TO ORDER",
        "APPROVAL OF MINUTES",
        "Approval of minutes: June 2026 Regular Meeting",
        "NEW BUSINESS",
        "Resolution 2026-14 sidewalk repair",
        "Discussion: parking study",
        "ADJOURNMENT",
    ]


# --- not found: a bad agenda id must not claim the tenant is missing ---


def test_get_agenda_raises_not_found_on_404():
    with pytest.raises(NotFoundError):
        status_client(404).get_agenda(999999999)


def test_get_agenda_raises_not_found_when_api_answers_empty_agenda():
    # The live API answers unknown numeric agenda ids with HTTP 200 and an
    # empty/default payload (id 0, no items) rather than a 404.
    client = status_client(200, {"id": 0, "items": [], "publishedFiles": []})

    with pytest.raises(NotFoundError):
        client.get_agenda(999999999)


# --- lenient parsing and raw preservation ---


def test_agenda_item_tolerates_minimal_payload():
    item = AgendaItem.from_api({"id": 1})

    assert item.item_id == 1
    assert item.name is None
    assert item.is_section is False
    assert item.sort_order is None
    assert item.attachments == []
    assert item.children == []
    assert item.raw == {"id": 1}


def test_agenda_preserves_raw_payload():
    raw = load_fixture("agenda.json")

    agenda = Agenda.from_api(raw)

    assert agenda.raw == raw
    assert agenda.items[0].raw == raw["items"][0]
