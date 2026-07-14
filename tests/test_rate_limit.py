"""Pacing slice: the client spaces requests politely by default."""

from pathlib import Path

import httpx
import pytest

import libcivicclerk.client
from libcivicclerk import CivicClerkClient


def default_paced_client() -> CivicClerkClient:
    """A client with the pacing default intact (conftest helpers disable it)."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CivicClerkClient("exampletown", http_client=http)


class FakeClock:
    """Stand-in for the time module: sleeps advance the clock instantly."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(libcivicclerk.client, "time", fake)
    return fake


def test_back_to_back_requests_are_paced_by_default(clock):
    client = default_paced_client()

    client.get_event_categories()
    client.get_event_categories()

    assert clock.sleeps == [pytest.approx(0.25)]  # first request never waits


def test_no_wait_when_interval_already_elapsed(clock):
    client = default_paced_client()

    client.get_event_categories()
    clock.now += 5.0
    client.get_event_categories()

    assert clock.sleeps == []


def test_custom_interval_is_honored(clock):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CivicClerkClient("exampletown", http_client=http, min_request_interval=2.0)

    client.get_event_categories()
    client.get_event_categories()

    assert clock.sleeps == [pytest.approx(2.0)]


def test_zero_interval_disables_pacing(clock):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CivicClerkClient("exampletown", http_client=http, min_request_interval=0)

    client.get_event_categories()
    client.get_event_categories()

    assert clock.sleeps == []


def test_downloads_are_paced_too(clock, tmp_path: Path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 data")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = CivicClerkClient("exampletown", http_client=http)

    client.download_file(1, tmp_path / "a.pdf")
    client.download_file(2, tmp_path / "b.pdf")

    assert clock.sleeps == [pytest.approx(0.25)]
