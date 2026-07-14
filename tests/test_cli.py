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
