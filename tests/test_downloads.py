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


def test_open_file_raises_not_found_on_entry_when_content_length_is_zero():
    # The API says "unavailable" with HTTP 200 and a 0-byte body. The caller
    # never touches iter_bytes here: entry alone must raise, or a caller who
    # only inspects headers would happily write a 0-byte PDF.
    client = stream_client(b"")

    with pytest.raises(NotFoundError), client.open_file(999999):
        pass  # pragma: no cover — entering the stream must raise


def test_iter_bytes_yields_the_whole_body_when_content_length_is_known():
    client = stream_client(b"%PDF-1.4 fake pdf bytes")

    with client.open_file(123) as stream:
        assert b"".join(stream.iter_bytes()) == b"%PDF-1.4 fake pdf bytes"


def test_iter_bytes_replays_the_chunk_peeked_at_entry():
    # Entry reads the first chunk to prove the body is non-empty. If that
    # chunk is not replayed here, every chunked download silently loses its
    # first chunk.
    class ChunkedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"first chunk "
            yield b"second chunk "
            yield b"third chunk"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=ChunkedStream())

    with mock_client(handler).open_file(123) as stream:
        assert stream.size is None  # chunked: emptiness was settled by reading
        assert b"".join(stream.iter_bytes()) == b"first chunk second chunk third chunk"


def test_open_file_raises_not_found_on_entry_when_chunked_body_is_empty():
    # Same trap, but the server declares no Content-Length, so emptiness can
    # only be discovered by reading the first chunk.
    class EmptyChunkedStream(httpx.SyncByteStream):
        def __iter__(self):
            return iter(())

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=EmptyChunkedStream())

    with pytest.raises(NotFoundError), mock_client(handler).open_file(999999):
        pass  # pragma: no cover — entering the stream must raise


# --- save: writes exactly the path it was handed ---


def test_save_writes_the_body_and_returns_the_destination(tmp_path):
    client = stream_client(b"%PDF-1.4 fake pdf bytes")
    destination = tmp_path / "agenda.pdf"

    with client.open_file(123) as stream:
        result = stream.save(destination)

    assert result == destination
    assert destination.read_bytes() == b"%PDF-1.4 fake pdf bytes"


def test_save_leaves_an_extensionless_destination_extensionless(tmp_path):
    # The library never edits the path the caller chose, even when the
    # stream knows a suffix the destination lacks.
    client = stream_client(b"bytes")
    destination = tmp_path / "no-extension-please"

    with client.open_file(123) as stream:
        assert stream.suffix == ".pdf"
        result = stream.save(destination)

    assert result == destination
    assert destination.read_bytes() == b"bytes"
    assert not (tmp_path / "no-extension-please.pdf").exists()


def test_save_interrupted_mid_stream_leaves_no_partial_file(tmp_path):
    class DropsMidStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial bytes"
            raise httpx.ReadError("connection lost")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=DropsMidStream())

    destination = tmp_path / "interrupted.pdf"

    with pytest.raises(NetworkError):  # noqa: SIM117 — the with blocks nest by design
        with mock_client(handler).open_file(123) as stream:
            stream.save(destination)

    assert not destination.exists()


def test_a_mid_body_drop_raises_network_error_inside_the_with_block(tmp_path):
    # httpx must not leak: a caller catching NetworkError around save() has
    # to see it there, not only once the with block exits.
    class DropsMidStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial bytes"
            raise httpx.ReadError("connection lost")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=DropsMidStream())

    with mock_client(handler).open_file(123) as stream:  # noqa: SIM117
        # Deliberately nested: pytest.raises must sit inside the stream's
        # with block, or this would not prove where the error surfaces.
        with pytest.raises(NetworkError):
            stream.save(tmp_path / "interrupted.pdf")

    assert not (tmp_path / "interrupted.pdf").exists()


def test_caller_composes_a_filename_from_the_model_name_and_the_stream_suffix(tmp_path):
    # The whole point of the feature: the name is the caller's, the
    # extension is the response's, and they meet inside the with block.
    client = headers_client(
        {"content-type": "application/pdf", "content-disposition": "attachment; filename=123.pdf"}
    )

    with client.open_file(123) as stream:
        saved = stream.save(tmp_path / f"Regular Meeting Agenda{stream.suffix}")

    assert saved.name == "Regular Meeting Agenda.pdf"
    assert saved.read_bytes() == b"body"


# --- suffix: the extension comes from the response, never from a guess ---


def headers_client(headers: dict[str, str], *, body: bytes = b"body") -> CivicClerkClient:
    """Client answering with exactly ``headers`` — no content-type unless given."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers=headers)

    return mock_client(handler)


def test_suffix_comes_from_the_content_disposition_filename():
    # What a real meeting file sends: the filename is only the numeric id
    # restated, but its extension is truthful.
    client = headers_client(
        {"content-type": "application/pdf", "content-disposition": "attachment; filename=123.pdf"}
    )

    with client.open_file(123) as stream:
        assert stream.suffix == ".pdf"


def test_suffix_prefers_the_content_disposition_filename_over_the_content_type():
    client = headers_client(
        {"content-type": "application/pdf", "content-disposition": 'attachment; filename="m.docx"'}
    )

    with client.open_file(123) as stream:
        assert stream.suffix == ".docx"


def test_suffix_falls_back_to_the_content_type():
    client = headers_client({"content-type": "application/pdf"})

    with client.open_file(123) as stream:
        assert stream.suffix == ".pdf"


def test_suffix_falls_back_to_the_url_path():
    # What a real agenda attachment sends: no content-disposition, a type
    # nothing can be guessed from, but a blob URL whose GUID path still ends
    # in a real extension.
    attachment = AgendaAttachment(
        attachment_id=1,
        file_name="Minutes",
        download_url=(
            "https://exampletown.blob.core.windows.net/stream/"
            "0f9a1b2c-3d4e-5f60-7182-93a4b5c6d7e8.pdf?sig=abc"
        ),
    )
    client = headers_client({"content-type": "application/x-unrecognized-type"})

    with client.open_attachment(attachment) as stream:
        assert stream.suffix == ".pdf"


def test_suffix_is_none_when_nothing_gives_a_basis_for_one():
    # No extension beats guessing .pdf and being silently wrong.
    client = headers_client({})

    with client.open_file(123) as stream:
        assert stream.content_type is None
        assert stream.suffix is None


# --- open_attachment: the same, for an attachment's signed blob URL ---


def test_open_attachment_streams_from_the_signed_url():
    seen: list[httpx.Request] = []
    client = recording_bytes_client(b"attachment bytes", seen)
    url = "https://exampletown.blob.core.windows.net/stream/minutes.pdf?sig=abc"
    attachment = AgendaAttachment(attachment_id=1, file_name="Minutes", download_url=url)

    with client.open_attachment(attachment) as stream:
        assert stream.content_type == "application/pdf"
        assert b"".join(stream.iter_bytes()) == b"attachment bytes"

    assert str(seen[0].url) == url


def test_open_attachment_raises_value_error_for_link_attachment():
    client = stream_client(b"")
    attachment = AgendaAttachment(
        attachment_id=2, file_name="Related news article", is_link=True, download_url=None
    )

    with pytest.raises(ValueError):
        client.open_attachment(attachment)  # eagerly, without entering a with block


def test_open_attachment_raises_not_found_on_entry_when_body_is_empty():
    client = stream_client(b"")
    attachment = AgendaAttachment(
        attachment_id=3, download_url="https://exampletown.blob.core.windows.net/x.pdf?sig=abc"
    )

    with pytest.raises(NotFoundError), client.open_attachment(attachment):
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
