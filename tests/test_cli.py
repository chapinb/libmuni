"""CLI slice: the civicclerk command demonstrates the library surface."""

import json

import httpx
import pytest
from conftest import load_fixture

from libcivicclerk import CivicClerkClient
from libcivicclerk.cli import main


def factory_for(handler):
    """A client factory serving canned responses — the CLI's test seam."""

    def factory(tenant: str) -> CivicClerkClient:
        return CivicClerkClient(
            tenant,
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            min_request_interval=0,
        )

    return factory


def payload_factory(payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return factory_for(handler)


# --- categories (slice 1 tracer) ---


def test_categories_lists_boards_human_readable(capsys):
    factory = payload_factory(load_fixture("event_categories.json"))

    exit_code = main(["categories", "exampletown"], client_factory=factory)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "11" in out
    assert "Town Council" in out
    assert "Planning Board" in out


def test_categories_json_emits_raw_payloads(capsys):
    factory = payload_factory(load_fixture("event_categories.json"))

    exit_code = main(["categories", "exampletown", "--json"], client_factory=factory)

    assert exit_code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed[0]["categoryDesc"] == "Town Council"  # raw API keys, not model fields


def test_library_errors_exit_nonzero_without_traceback(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    exit_code = main(["categories", "nosuchtown"], client_factory=factory_for(handler))

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error:" in captured.err
    assert "nosuchtown" in captured.err
    assert "Traceback" not in captured.err


def test_unknown_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main(["frobnicate", "exampletown"])

    assert excinfo.value.code == 2


# --- events (slice 2) ---


def test_events_lists_meetings(capsys):
    factory = payload_factory(load_fixture("events.json"))

    exit_code = main(["events", "exampletown"], client_factory=factory)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Town Council Regular Meeting" in out
    assert "2026-08-03" in out


def test_events_limit_stops_output_and_requests(capsys):
    base = "https://exampletown.api.civicclerk.com/v1/Events"
    pages = [
        {
            "value": [
                {"id": 1, "eventDate": "2026-07-01T19:00:00Z", "eventName": "First"},
                {"id": 2, "eventDate": "2026-07-02T19:00:00Z", "eventName": "Second"},
            ],
            "@odata.nextLink": f"{base}?$skiptoken=page-1",
        },
        {"value": [{"id": 3, "eventDate": "2026-07-03T19:00:00Z", "eventName": "Third"}]},
    ]
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        page = 1 if request.url.params.get("$skiptoken") else 0
        return httpx.Response(200, json=pages[page])

    exit_code = main(["events", "exampletown", "--limit", "2"], client_factory=factory_for(handler))

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Second" in out
    assert "Third" not in out
    assert len(requests_seen) == 1  # the second page is never fetched


def test_events_filters_reach_the_request(capsys):
    requests_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(request)
        return httpx.Response(200, json={"value": []})

    exit_code = main(
        [
            "events",
            "exampletown",
            "--category",
            "12",
            "--from",
            "2026-07-01",
            "--to",
            "2026-08-01",
        ],
        client_factory=factory_for(handler),
    )

    assert exit_code == 0
    filter_expr = requests_seen[0].url.params["$filter"]
    assert "categoryId eq 12" in filter_expr
    assert "2026-07-01" in filter_expr
    assert "2026-08-01" in filter_expr


def test_events_invalid_date_is_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main(["events", "exampletown", "--from", "July 1st"])

    assert excinfo.value.code == 2
