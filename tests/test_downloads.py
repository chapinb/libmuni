"""Download slice: meeting-level files and agenda attachments stream to
disk, and best-effort plain text extraction is available.

The live API returns HTTP 200 with a 0-byte body for both invalid file ids
and files with no extractable text — never a clean 404 — so every download
path treats an empty body as "unavailable" rather than trusting the status
code alone.
"""

import httpx
import pytest

from libcivicclerk import AgendaAttachment, CivicClerkClient, NetworkError, NotFoundError


def stream_client(
    body: bytes, *, content_type: str = "application/pdf", status_code: int = 200
) -> CivicClerkClient:
    """Client whose transport always answers with a fixed body/status."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, content=body, headers={"content-type": content_type})

    return CivicClerkClient(
        "exampletown", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def recording_client(body: bytes, seen_requests: list[httpx.Request]) -> CivicClerkClient:
    """Client whose transport records every request and serves ``body``."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(200, content=body, headers={"content-type": "application/pdf"})

    return CivicClerkClient(
        "exampletown", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )


# --- download_file: meeting-level files by PublishedFile.file_id ---


def test_download_file_writes_bytes_and_returns_destination(tmp_path):
    client = stream_client(b"%PDF-1.4 fake pdf bytes")
    destination = tmp_path / "agenda.pdf"

    result = client.download_file(123, destination)

    assert result == destination
    assert destination.read_bytes() == b"%PDF-1.4 fake pdf bytes"


def test_download_file_requests_meeting_file_stream_endpoint(tmp_path):
    seen: list[httpx.Request] = []
    recording_client(b"data", seen).download_file(42, tmp_path / "f.pdf")

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

    client = CivicClerkClient(
        "exampletown", http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    destination = tmp_path / "interrupted.pdf"

    with pytest.raises(NetworkError):
        client.download_file(123, destination)

    assert not destination.exists()  # docstring promises no partial file


def test_download_file_raises_not_found_on_404(tmp_path):
    client = stream_client(b"", status_code=404)
    destination = tmp_path / "missing.pdf"

    with pytest.raises(NotFoundError):
        client.download_file(999999, destination)

    assert not destination.exists()


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
    recording_client(b"text", seen).get_file_text(42)

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
