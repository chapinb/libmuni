"""User-Agent slice: requests identify the library and its version."""

import httpx
from conftest import recording_client

import libcivicclerk
from libcivicclerk import CivicClerkClient

LIBRARY_USER_AGENT = (
    f"libcivicclerk/{libcivicclerk.__version__} (+https://github.com/chapinb/libcivicclerk)"
)


def test_requests_carry_library_user_agent():
    # conftest injects a plain httpx.Client (no caller User-Agent), so the
    # library identifies itself instead of leaving httpx's default.
    seen: list[httpx.Request] = []
    recording_client({"value": []}, seen).get_event_categories()

    assert seen[0].headers["user-agent"] == LIBRARY_USER_AGENT


def test_owned_client_carries_library_user_agent():
    client = CivicClerkClient("exampletown")
    try:
        assert client._http.headers["user-agent"] == LIBRARY_USER_AGENT
    finally:
        client.close()


def test_caller_set_user_agent_is_preserved():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": "my-app/2.0"},
    )
    with CivicClerkClient("exampletown", http_client=http) as client:
        client.get_event_categories()

    assert seen[0].headers["user-agent"] == "my-app/2.0"


def test_version_is_a_release_string():
    major, minor, *_ = libcivicclerk.__version__.split(".")
    assert major.isdigit()
    assert minor.isdigit()
