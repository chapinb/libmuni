"""Error-model slice: failures surface as typed, catchable library errors."""

import httpx
import pytest
from conftest import mock_client

from libmuni.civicclerk import (
    APIStatusError,
    CivicClerkError,
    EventCategory,
    NetworkError,
    PayloadError,
    UnknownTenantError,
)


def test_server_error_raises_api_status_error_with_details():
    client = mock_client(lambda request: httpx.Response(500, text="boom"))

    with pytest.raises(APIStatusError) as excinfo:
        client.get_event_categories()

    assert excinfo.value.status_code == 500
    assert "EventCategories" in str(excinfo.value)


def test_network_failure_raises_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(NetworkError):
        mock_client(handler).get_event_categories()


def test_404_on_always_present_endpoint_means_unknown_tenant():
    client = mock_client(lambda request: httpx.Response(404))

    with pytest.raises(UnknownTenantError) as excinfo:
        client.get_event_categories()

    assert "exampletown" in str(excinfo.value)


def test_non_json_success_body_raises_payload_error():
    client = mock_client(lambda request: httpx.Response(200, text="<html>maintenance</html>"))

    with pytest.raises(PayloadError):
        client.get_event_categories()


@pytest.mark.parametrize("payload", [None, [], 42, "categories"])
def test_non_object_json_success_body_raises_payload_error(payload):
    client = mock_client(lambda request: httpx.Response(200, json=payload))

    with pytest.raises(PayloadError):
        client.get_event_categories()


def test_non_utf8_json_success_body_raises_payload_error():
    client = mock_client(lambda request: httpx.Response(200, content=b"\xff"))

    with pytest.raises(PayloadError):
        client.get_event_categories()


def test_malformed_continuation_payload_redacts_url_credentials():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={
                    "value": [],
                    "@odata.nextLink": (
                        "https://user:password@blob.example/events?skip=1&sig=TOPSECRET#private"
                    ),
                },
            )
        return httpx.Response(200, text="not JSON")

    client = mock_client(handler)

    with pytest.raises(PayloadError) as excinfo:
        list(client.iter_events())

    assert str(excinfo.value) == "response from https://blob.example/events is not valid JSON"


@pytest.mark.parametrize("value", [None, {}, 7, "categories"])
def test_non_array_collection_value_raises_payload_error(value):
    client = mock_client(lambda request: httpx.Response(200, json={"value": value}))

    with pytest.raises(PayloadError):
        client.get_event_categories()


def test_missing_load_bearing_field_raises_payload_error_naming_it():
    with pytest.raises(PayloadError) as excinfo:
        EventCategory.from_api({"categoryDesc": "Town Council"})

    assert "id" in str(excinfo.value)


def test_all_library_errors_share_one_base():
    for error_type in (APIStatusError, NetworkError, PayloadError, UnknownTenantError):
        assert issubclass(error_type, CivicClerkError)
