"""Download slice: meeting-level files and agenda attachments stream to
disk, and best-effort plain text extraction is available.

The live API returns HTTP 200 with a 0-byte body for both invalid file ids
and files with no extractable text — never a clean 404 — so every download
path treats an empty body as "unavailable" rather than trusting the status
code alone.
"""

import httpx
import pytest
from conftest import mock_client

from libcivicclerk import AgendaAttachment, CivicClerkClient, NetworkError, NotFoundError


def stream_client(
    body: bytes, *, content_type: str = "application/pdf", status_code: int = 200
) -> CivicClerkClient:
    """Client whose transport always answers with a fixed body/status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=body, headers={"content-type": content_type})

    return mock_client(handler)


def recording_bytes_client(body: bytes, seen_requests: list[httpx.Request]) -> CivicClerkClient:
    """Client whose transport records every request and serves ``body``."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    return mock_client(handler)


def test_owned_client_follows_redirects():
    # File streams are commonly served as a redirect to storage, so the
    # client the library creates for itself must follow them.
    client = CivicClerkClient("exampletown")
    try:
        assert client._http.follow_redirects is True
    finally:
        client.close()


# --- download_file: meeting-level files by PublishedFile.file_id ---


def test_download_file_writes_bytes_and_returns_destination(tmp_path):
    client = stream_client(b"%PDF-1.4 fake pdf bytes")
    destination = tmp_path / "agenda.pdf"

    result = client.download_file(123, destination)

    assert result == destination
    assert destination.read_bytes() == b"%PDF-1.4 fake pdf bytes"


def test_download_file_requests_meeting_file_stream_endpoint(tmp_path):
    seen: list[httpx.Request] = []
    recording_bytes_client(b"data", seen).download_file(42, tmp_path / "f.pdf")

    assert str(seen[0].url) == (
        "https://exampletown.api.civicclerk.com/v1/Meetings/"
        "GetMeetingFileStream(fileId=42,plainText=false)"
    )


def test_download_file_raises_not_found_on_empty_body_and_leaves_no_file(tmp_path):
    client = stream_client(b"")
    destination = tmp_path / "missing.pdf"

    with pytest.raises(NotFoundError):
        client.download_file(999999, destination)

    assert not destination.exists()


def test_download_file_interrupted_mid_stream_leaves_no_partial_file(tmp_path):
    class DropsMidStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial bytes"
            raise httpx.ReadError("connection lost")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=DropsMidStream())

    client = mock_client(handler)
    destination = tmp_path / "interrupted.pdf"

    with pytest.raises(NetworkError):
        client.download_file(123, destination)

    assert not destination.exists()  # docstring promises no partial file


def test_failed_download_never_deletes_a_preexisting_file(tmp_path):
    destination = tmp_path / "existing.pdf"
    destination.write_bytes(b"precious earlier download")
    client = stream_client(b"", status_code=404)

    with pytest.raises(NotFoundError):
        client.download_file(999999, destination)

    assert destination.read_bytes() == b"precious earlier download"


def test_download_file_raises_not_found_on_404(tmp_path):
    client = stream_client(b"", status_code=404)
    destination = tmp_path / "missing.pdf"

    with pytest.raises(NotFoundError):
        client.download_file(999999, destination)

    assert not destination.exists()


# --- open_file: inspect the response before choosing a destination ---


def test_open_file_reports_content_type_and_size():
    client = stream_client(b"%PDF-1.4 fake pdf bytes")

    with client.open_file(123) as stream:
        assert stream.content_type == "application/pdf"
        assert stream.size == len(b"%PDF-1.4 fake pdf bytes")


def test_open_file_strips_content_type_parameters():
    client = stream_client(b"some text", content_type="text/plain; charset=utf-8")

    with client.open_file(123) as stream:
        assert stream.content_type == "text/plain"


def test_open_file_requests_meeting_file_stream_endpoint():
    seen: list[httpx.Request] = []

    with recording_bytes_client(b"data", seen).open_file(42):
        pass

    assert str(seen[0].url) == (
        "https://exampletown.api.civicclerk.com/v1/Meetings/"
        "GetMeetingFileStream(fileId=42,plainText=false)"
    )


def test_open_file_reports_no_size_when_server_streams_chunked():
    class ChunkedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"chunk one "
            yield b"chunk two"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkedStream())

    with mock_client(handler).open_file(123) as stream:
        assert stream.size is None


def test_open_file_raises_not_found_on_404():
    client = stream_client(b"", status_code=404)

    with pytest.raises(NotFoundError), client.open_file(999999):
        pass  # pragma: no cover — entering the stream must raise


# --- download_attachment: agenda attachments via their signed download_url ---


def test_download_attachment_writes_bytes_and_returns_destination(tmp_path):
    client = stream_client(b"attachment bytes")
    attachment = AgendaAttachment(
        attachment_id=1,
        file_name="Minutes",
        download_url="https://exampletown.blob.core.windows.net/stream/minutes.pdf?sig=abc",
    )
    destination = tmp_path / "minutes.pdf"

    result = client.download_attachment(attachment, destination)

    assert result == destination
    assert destination.read_bytes() == b"attachment bytes"


def test_download_attachment_raises_value_error_for_link_attachment(tmp_path):
    client = stream_client(b"")
    attachment = AgendaAttachment(
        attachment_id=2, file_name="Related news article", is_link=True, download_url=None
    )

    with pytest.raises(ValueError):
        client.download_attachment(attachment, tmp_path / "x.pdf")


def test_download_attachment_raises_not_found_on_empty_body_and_leaves_no_file(tmp_path):
    client = stream_client(b"")
    attachment = AgendaAttachment(
        attachment_id=3, download_url="https://exampletown.blob.core.windows.net/x.pdf?sig=abc"
    )
    destination = tmp_path / "x.pdf"

    with pytest.raises(NotFoundError):
        client.download_attachment(attachment, destination)

    assert not destination.exists()


# --- get_file_text: best-effort plain text extraction ---


def test_get_file_text_returns_decoded_text():
    client = stream_client(b"Hello agenda text", content_type="text/plain; charset=utf-8")

    assert client.get_file_text(123) == "Hello agenda text"


def test_get_file_text_requests_plain_text_variant():
    seen: list[httpx.Request] = []
    recording_bytes_client(b"text", seen).get_file_text(42)

    assert str(seen[0].url) == (
        "https://exampletown.api.civicclerk.com/v1/Meetings/"
        "GetMeetingFileStream(fileId=42,plainText=true)"
    )


def test_get_file_text_returns_none_on_empty_body():
    client = stream_client(b"", content_type="text/plain")

    assert client.get_file_text(123) is None


def test_get_file_text_raises_not_found_on_404():
    client = stream_client(b"", status_code=404)

    with pytest.raises(NotFoundError):
        client.get_file_text(999999)
