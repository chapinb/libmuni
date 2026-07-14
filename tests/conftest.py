"""Shared test helpers: fixture loading and mock-transport client wiring."""

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from libcivicclerk import CivicClerkClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Return the parsed JSON fixture stored at tests/fixtures/<name>."""
    return json.loads((FIXTURES / name).read_text())


def mock_client(
    handler: Callable[[httpx.Request], httpx.Response], *, tenant: str = "exampletown"
) -> CivicClerkClient:
    """A client for ``tenant`` answered by ``handler`` — no real HTTP.

    Pacing is disabled so multi-request tests don't really sleep; the
    pacing behavior itself is covered by test_rate_limit.py.
    """
    transport = httpx.MockTransport(handler)
    return CivicClerkClient(
        tenant, http_client=httpx.Client(transport=transport), min_request_interval=0
    )


def recording_client(payload: dict, seen_requests: list[httpx.Request]) -> CivicClerkClient:
    """Client that records every request and answers 200 with ``payload`` as JSON."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, json=payload)

    return mock_client(handler)
