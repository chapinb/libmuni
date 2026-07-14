"""An open response body, exposed before the caller commits to a filename.

The naming information a caller needs — content type, extension, size —
only exists once the response headers arrive, and the API offers no way to
ask ahead of time (``HEAD`` answers 405). ``FileStream`` is the object that
hands those headers over at the one moment they are actionable: after they
arrive, before the body is read.

Unlike the models, ``FileStream`` is mutable and lifetime-bound: it wraps a
live HTTP response and is only valid inside the ``with`` block that yielded
it.
"""

from collections.abc import Iterator

import httpx

from libcivicclerk.errors import NotFoundError


class FileStream:
    """A file's response headers and body, open and not yet consumed.

    Obtained from ``CivicClerkClient.open_file`` or ``open_attachment``,
    and valid only inside their ``with`` block — the response closes on
    exit.

    Args:
        response: The open, streaming response to wrap.

    Raises:
        NotFoundError: If the body is empty, which the API uses to mean
            "unavailable". Detected as the stream is opened, before the
            caller sees it.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self._chunks = response.iter_bytes()
        self._buffered: bytes | None = self._read_first_chunk()

    def _read_first_chunk(self) -> bytes:
        """Return the body's first chunk, proving the body is not empty.

        The API answers an unavailable file with HTTP 200 and a 0-byte
        body, so emptiness has to be settled before the caller is handed
        the stream — otherwise a caller who only reads the headers would
        write a 0-byte file. ``Content-Length: 0`` is decisive; when the
        header is absent, the only way to know is to read.

        The chunk is buffered rather than discarded, and ``iter_bytes``
        replays it as the body's first chunk.

        Raises:
            NotFoundError: If the body is empty.
        """
        if self._response.headers.get("content-length") == "0":
            raise self._unavailable()
        for chunk in self._chunks:
            if chunk:
                return chunk
        raise self._unavailable()

    def _unavailable(self) -> NotFoundError:
        """The error for an empty body — the API's way of saying "no such file"."""
        url = str(self._response.request.url)
        return NotFoundError(
            f"file at {url} is unavailable (empty response body)",
            status_code=200,
            url=url,
        )

    def iter_bytes(self) -> Iterator[bytes]:
        """Yield the body in non-empty chunks, starting from its first byte.

        Includes the chunk read at entry to prove the body was not empty,
        so no bytes are lost. The body is read from the network as it is
        consumed and cannot be rewound: this is a single pass, and calling
        it again yields only what is left. Valid only inside the ``with``
        block that yielded this stream.

        Raises:
            NetworkError: If the connection fails partway through the body.
        """
        if self._buffered is not None:
            first, self._buffered = self._buffered, None
            yield first
        for chunk in self._chunks:
            if chunk:
                yield chunk

    @property
    def content_type(self) -> str | None:
        """The response's media type, e.g. ``application/pdf``.

        Parameters such as ``charset`` are stripped. ``None`` when the
        response carries no ``Content-Type``.
        """
        header = self._response.headers.get("content-type")
        if not header:
            return None
        return header.split(";", 1)[0].strip().lower() or None

    @property
    def size(self) -> int | None:
        """The body's size in bytes, from ``Content-Length``.

        ``None`` when the server streams the response chunked and so does
        not declare a length up front.
        """
        header = self._response.headers.get("content-length")
        if header is None:
            return None
        try:
            return int(header)
        except ValueError:
            return None
