"""CLI slice: the civicclerk command demonstrates the library surface."""

import json

import httpx
import pytest
from conftest import load_fixture, mock_client

from libmuni.civicclerk import CivicClerkClient
from libmuni.civicclerk.cli import main
from libmuni.cli import _PLATFORMS as muni_platforms
from libmuni.cli import main as muni_main


def factory_for(handler):
    """A client factory serving canned responses — the CLI's test seam."""

    def factory(tenant: str) -> CivicClerkClient:
        return mock_client(handler, tenant=tenant)

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


# --- agenda, text, download (slice 3) ---


def test_agenda_prints_indented_tree_with_attachment_counts(capsys):
    factory = payload_factory(load_fixture("agenda.json"))

    exit_code = main(["agenda", "exampletown", "7301"], client_factory=factory)

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "CALL TO ORDER" in out
    nested = "  Resolution 2026-14 sidewalk repair"
    assert nested in out  # items indent under their section
    assert "2 attachments" in out
    assert out.index("NEW BUSINESS") < out.index("Resolution 2026-14 sidewalk repair")


def test_text_prints_extracted_text(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="MINUTES OF THE JUNE MEETING")

    exit_code = main(["text", "exampletown", "9001"], client_factory=factory_for(handler))

    assert exit_code == 0
    assert "MINUTES OF THE JUNE MEETING" in capsys.readouterr().out


def test_text_none_reports_to_stderr_and_keeps_stdout_clean(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="")

    exit_code = main(["text", "exampletown", "9001"], client_factory=factory_for(handler))

    captured = capsys.readouterr()
    assert exit_code == 0  # no text is within the API's contract, not an error
    assert captured.out == ""
    assert "no text" in captured.err


def test_download_writes_file_and_reports_destination(capsys, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 fake")

    destination = tmp_path / "packet.pdf"
    exit_code = main(
        ["download", "exampletown", "9001", str(destination)],
        client_factory=factory_for(handler),
    )

    assert exit_code == 0
    assert destination.read_bytes() == b"%PDF-1.4 fake"
    assert str(destination) in capsys.readouterr().out


# --- CLI-boundary failure modes ---


def test_download_os_errors_are_clean_errors(capsys, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 fake")

    destination = tmp_path / "no" / "such" / "dir" / "packet.pdf"
    exit_code = main(
        ["download", "exampletown", "9001", str(destination)],
        client_factory=factory_for(handler),
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "error:" in captured.err
    assert "Traceback" not in captured.err


def test_negative_limit_is_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main(["events", "exampletown", "--limit", "-5"])

    assert excinfo.value.code == 2


def test_keyboard_interrupt_exits_quietly(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        raise KeyboardInterrupt

    exit_code = main(["categories", "exampletown"], client_factory=factory_for(handler))

    captured = capsys.readouterr()
    assert exit_code == 130
    assert "interrupted" in captured.err
    assert "Traceback" not in captured.err


def test_broken_pipe_exits_without_noise(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        raise BrokenPipeError

    exit_code = main(["categories", "exampletown"], client_factory=factory_for(handler))

    assert exit_code == 1
    assert "Traceback" not in capsys.readouterr().err


# --- demo tour (slice 4) ---


def tenant_handler(request: httpx.Request) -> httpx.Response:
    """Route requests like a real tenant with full data."""
    path = request.url.path
    if "EventCategories" in path:
        return httpx.Response(200, json=load_fixture("event_categories.json"))
    if "GetMeetingFileStream" in path:
        return httpx.Response(200, text="MINUTES OF THE JUNE MEETING")
    if "/Meetings/" in path:
        return httpx.Response(200, json=load_fixture("agenda.json"))
    return httpx.Response(200, json=load_fixture("events.json"))


def test_demo_walks_the_full_surface(capsys):
    exit_code = main(["demo", "exampletown"], client_factory=factory_for(tenant_handler))

    out = capsys.readouterr().out
    assert exit_code == 0
    # every step ran, with its Python equivalent narrated
    assert "client.get_event_categories()" in out
    assert "Town Council" in out
    assert "client.iter_events(" in out
    assert "client.get_agenda(7301)" in out
    assert "NEW BUSINESS" in out
    assert "client.get_file_text(9001)" in out
    assert "MINUTES OF THE JUNE MEETING" in out
    assert ".raw" in out  # closing pointer to the escape hatch


def test_demo_skips_gracefully_when_tenant_has_no_extras(capsys):
    bare_event = {"id": 1, "eventDate": "2026-07-01T19:00:00Z", "eventName": "Budget Hearing"}

    def handler(request: httpx.Request) -> httpx.Response:
        if "EventCategories" in request.url.path:
            return httpx.Response(200, json=load_fixture("event_categories.json"))
        return httpx.Response(200, json={"value": [bare_event]})

    exit_code = main(["demo", "exampletown"], client_factory=factory_for(handler))

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "Budget Hearing" in out
    assert "no published agenda" in out
    assert "no published files" in out


# --- muni dispatcher (slice 3): routes to the platform CLI ---


def test_muni_forwards_remaining_args_to_the_platform_cli(monkeypatch):
    seen: list = []

    def spy(argv):
        seen.append(list(argv))
        return 7

    monkeypatch.setitem(muni_platforms, "civicclerk", spy)

    exit_code = muni_main(["civicclerk", "events", "exampletown"])

    assert exit_code == 7  # the platform CLI's exit code propagates
    assert seen == [["events", "exampletown"]]  # platform token stripped


def test_muni_lists_platforms_in_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        muni_main(["--help"])

    assert excinfo.value.code == 0
    assert "civicclerk" in capsys.readouterr().out


def test_muni_no_platform_is_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        muni_main([])

    assert excinfo.value.code == 2


def test_muni_unknown_platform_is_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        muni_main(["frobnicate"])

    assert excinfo.value.code == 2


def test_muni_civicclerk_help_shows_verbs_under_muni_prog(capsys):
    with pytest.raises(SystemExit) as excinfo:
        muni_main(["civicclerk", "--help"])

    out = capsys.readouterr().out
    assert excinfo.value.code == 0
    assert "muni civicclerk" in out  # usage line reflects how it was invoked
    assert "categories" in out
    assert "events" in out
