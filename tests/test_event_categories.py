"""Tracer slice: event categories reach the caller as typed models."""

import httpx
from conftest import load_fixture, mock_client, recording_client

from libcivicclerk import EventCategory

# --- acceptance: the full path from client call to typed models ---


def test_client_returns_typed_event_categories():
    client = recording_client(load_fixture("event_categories.json"), [])

    categories = client.get_event_categories()

    assert [c.name for c in categories] == ["Town Council", "Planning Board", "Parks Subcommittee"]
    assert categories[0].id == 11
    assert categories[0].is_public is True
    assert categories[2].is_public is False


def test_client_targets_the_tenant_subdomain():
    seen: list[httpx.Request] = []
    recording_client({"value": []}, seen).get_event_categories()

    assert str(seen[0].url) == "https://exampletown.api.civicclerk.com/v1/EventCategories"


# --- unit: parsing behavior ---


def test_parse_preserves_raw_payload():
    payload = load_fixture("event_categories.json")

    categories = recording_client(payload, []).get_event_categories()

    assert categories[0].raw == payload["value"][0]
    assert categories[0].raw["timeStamp"] == "AAAAAAAQAAA="


def test_parse_normalizes_missing_parent_to_none():
    categories = recording_client(load_fixture("event_categories.json"), []).get_event_categories()

    assert categories[0].parent_id is None  # API encodes "no parent" as -1
    assert categories[2].parent_id == 11


def test_category_model_tolerates_missing_optional_fields():
    category = EventCategory.from_api({"id": 7})

    assert category.id == 7
    assert category.name is None
    assert category.sort_order is None
    assert category.is_public is None
    assert category.parent_id is None


def test_client_is_a_context_manager():
    with mock_client(lambda request: httpx.Response(200, json={"value": []})) as client:
        assert client.get_event_categories() == []
