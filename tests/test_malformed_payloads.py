"""Malformed payload shapes surface as PayloadError, never bare built-ins.

errors.py promises that ``except CivicClerkError`` catches anything the
library raises; a field that is present but the wrong shape (string id,
scalar where a list belongs) must keep that promise.
"""

import pytest

from libmuni.civicclerk import Agenda, CivicClerkError, Event, EventCategory, PayloadError


def test_non_numeric_id_raises_payload_error():
    with pytest.raises(PayloadError):
        EventCategory.from_api({"id": "abc"})


def test_malformed_optional_field_raises_payload_error():
    with pytest.raises(PayloadError):
        Event.from_api({"id": 1, "eventDate": "2026-01-05T19:00:00Z", "categoryId": "abc"})


def test_non_dict_event_location_raises_payload_error():
    with pytest.raises(PayloadError):
        Event.from_api({"id": 1, "eventDate": "2026-01-05T19:00:00Z", "eventLocation": "lobby"})


def test_non_list_published_files_raises_payload_error():
    with pytest.raises(PayloadError):
        Event.from_api({"id": 1, "eventDate": "2026-01-05T19:00:00Z", "publishedFiles": "nope"})


def test_non_list_agenda_items_raises_payload_error():
    with pytest.raises(PayloadError):
        Agenda.from_api({"id": 5, "items": 7})


def test_malformed_payload_errors_are_catchable_as_civicclerk_error():
    with pytest.raises(CivicClerkError):
        EventCategory.from_api({"id": "abc"})
