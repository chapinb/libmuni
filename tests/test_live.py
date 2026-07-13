"""Live contract tests: detect upstream API drift against a real tenant.

Deselected by default (see pyproject's ``addopts``); opt in with
``pytest -m live``. The tenant to test against comes from the
``CIVICCLERK_TEST_TENANT`` environment variable so no municipality is named
in this repository; the suite skips when it is unset.

These tests assert the *contract* this library relies on (shapes, paging,
error signals), not any tenant's data. Keep them few and polite — they make
real HTTP requests.
"""

import datetime as dt
import os

import pytest

from libcivicclerk import CivicClerkClient, NotFoundError, UnknownTenantError

TENANT = os.environ.get("CIVICCLERK_TEST_TENANT")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not TENANT, reason="CIVICCLERK_TEST_TENANT is not set"),
]


@pytest.fixture(scope="module")
def client():
    assert TENANT is not None
    with CivicClerkClient(TENANT) as live_client:
        yield live_client


@pytest.fixture(scope="module")
def recent_events(client):
    today = dt.date.today()
    return client.get_events(from_date=today - dt.timedelta(days=45), to_date=today)


def test_event_categories_parse(client):
    categories = client.get_event_categories()

    assert categories, "tenant publishes no categories — endpoint or parsing drifted"
    assert all(category.id for category in categories)
    assert any(category.name for category in categories)


def test_events_parse_with_wall_clock_datetimes(recent_events):
    assert isinstance(recent_events, list)
    for event in recent_events:
        assert event.id
        assert event.starts_at.tzinfo is None


def test_agenda_tree_walks(client, recent_events):
    with_agenda = [event for event in recent_events if event.agenda_id]
    if not with_agenda:
        pytest.skip("no recent event with a published agenda")

    agenda = client.get_agenda(with_agenda[0].agenda_id)

    items = list(agenda.walk_items())
    assert items, "agenda published but has no items — payload shape drifted"


def test_download_and_text_extraction(client, recent_events, tmp_path):
    with_files = [event for event in recent_events if event.published_files]
    if not with_files:
        pytest.skip("no recent event with published files")

    file = with_files[0].published_files[0]
    destination = client.download_file(file.file_id, tmp_path / "document.pdf")

    assert destination.stat().st_size > 500
    assert destination.read_bytes().startswith(b"%PDF")

    # Best-effort contract: text or None, never an exception for a real file.
    text = client.get_file_text(file.file_id)
    assert text is None or isinstance(text, str)


def test_nonexistent_agenda_raises_not_found(client):
    with pytest.raises(NotFoundError):
        client.get_agenda(999_999_999)


def test_unknown_tenant_raises():
    with CivicClerkClient("zz-no-such-tenant-zz") as bad_client, pytest.raises(UnknownTenantError):
        bad_client.get_event_categories()
