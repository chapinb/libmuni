"""Tracer slice: event categories reach the caller as typed models."""

import httpx
from conftest import load_fixture

from libcivicclerk import CivicClerkClient, EventCategory


def fixture_transport(payload: dict, expected_path: str) -> httpx.MockTransport:
    """Serve ``payload`` for requests to ``expected_path``, 404 otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == expected_path:
            return httpx.Response(200, json=payload)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def make_client(payload: dict, expected_path: str, tenant: str = "exampletown") -> CivicClerkClient:
    transport = fixture_transport(payload, expected_path)
    return CivicClerkClient(tenant, http_client=httpx.Client(transport=transport))


# --- acceptance: the full path from client call to typed models ---


def test_client_returns_typed_event_categories():
    client = make_client(load_fixture("event_categories.json"), "/v1/EventCategories")

    categories = client.get_event_categories()

    assert [c.name for c in categories] == ["Town Council", "Planning Board", "Parks Subcommittee"]
    assert categories[0].id == 11
    assert categories[0].is_public is True
    assert categories[2].is_public is False


def test_client_targets_the_tenant_subdomain():
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        return httpx.Response(200, json={"value": []})

    client = CivicClerkClient(
        "sometown", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    client.get_event_categories()

    assert seen_hosts == ["sometown.api.civicclerk.com"]


# --- unit: parsing behavior ---


def test_parse_preserves_raw_payload():
    payload = load_fixture("event_categories.json")
    client = make_client(payload, "/v1/EventCategories")

    categories = client.get_event_categories()

    assert categories[0].raw == payload["value"][0]
    assert categories[0].raw["timeStamp"] == "AAAAAAAQAAA="


def test_parse_normalizes_missing_parent_to_none():
    payload = load_fixture("event_categories.json")
    client = make_client(payload, "/v1/EventCategories")

    categories = client.get_event_categories()

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
    with make_client({"value": []}, "/v1/EventCategories") as client:
        assert client.get_event_categories() == []
