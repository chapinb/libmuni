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

import mimetypes
import os
import tempfile
from collections.abc import Iterator
from email.message import Message
from pathlib import Path, PurePosixPath

import httpx

from libcivicclerk.errors import NotFoundError, _network_error


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
        write a 0-byte file. A declared size of zero is decisive; when the
        server declares no size, the only way to know is to read.

        The chunk is buffered rather than discarded, and ``iter_bytes``
        replays it as the body's first chunk.

        Raises:
            NotFoundError: If the body is empty.
        """
        if self.size == 0:
            raise self._unavailable()
        while (chunk := self._next_chunk()) is not None:
            if chunk:
                return chunk
        raise self._unavailable()

    def _next_chunk(self) -> bytes | None:
        """Return the next chunk off the wire, or ``None`` at the end of the body.

        The one place the body is read, so the one place a transport
        failure while reading it becomes a ``NetworkError`` — whether it
        strikes on the first chunk (inside ``__init__``) or a later one
        (inside ``iter_bytes``). Reading the response is this object's job;
        the client only translates failures that happen before the response
        exists.
        """
        try:
            return next(self._chunks, None)
        except httpx.TransportError as exc:
            raise _network_error(str(self._response.request.url), exc) from exc

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
        while (chunk := self._next_chunk()) is not None:
            if chunk:
                yield chunk

    def save(self, destination: Path) -> Path:
        """Write the body to exactly ``destination`` and return it.

        The path is written verbatim: a destination with no extension is
        written with no extension, and nothing is appended or renamed. The
        stream's ``suffix`` is in scope inside the ``with`` block, so a
        caller who wants an extension composes it into the path themselves.

        Written in chunks to a sibling temporary file, so large files never
        load fully into memory and a completed download replaces
        ``destination`` atomically. If writing fails — including when the
        connection drops partway through — an existing destination is left
        untouched and no partial file remains. Valid only inside the ``with``
        block that yielded this stream, and only once: the body cannot be
        rewound.

        The body is written until the server stops sending; there is no
        size cap, so a hostile or broken endpoint can fill the destination
        disk. Bound it yourself — check ``size`` where the server declares
        one, or wrap ``iter_bytes`` with your own running-total limit — when
        writing from a tenant you do not fully trust.

        Args:
            destination: Local path to write the body to, used exactly as
                given.

        Returns:
            ``destination``, for chaining.

        Raises:
            NetworkError: If the connection fails partway through the body.
            OSError: If ``destination`` cannot be written.
        """
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                for chunk in self.iter_bytes():
                    file.write(chunk)
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        return destination

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
    def suffix(self) -> str | None:
        """The file's extension, leading dot included, e.g. ``.pdf``.

        Derived from the response, never guessed from the endpoint, and
        ``None`` when the response gives no basis for one — the API serves
        mostly PDFs, but assuming ``.pdf`` is silently wrong the day a
        tenant publishes something else. The bytes are not sniffed.

        Three sources, in order, because no single one covers both
        endpoints: the ``Content-Disposition`` filename (meeting files send
        one, and although the name is only the file's id restated, its
        extension is truthful); then the content type; then the extension
        on the request URL's path (which is what rescues attachments, whose
        signed blob URLs end in a real extension but carry no
        ``Content-Disposition``).

        Pair it with the caller-facing name — ``PublishedFile.name`` or
        ``AgendaAttachment.file_name``, neither of which has an extension —
        to compose a filename before calling ``save``.
        """
        return (
            self._suffix_from_disposition()
            or self._suffix_from_content_type()
            or self._suffix_from_url()
        )

    def _suffix_from_disposition(self) -> str | None:
        """The extension of the ``Content-Disposition`` filename, if it sent one."""
        header = self._response.headers.get("content-disposition")
        if not header:
            return None
        # Message parses the header's quoting and encoding rules for us.
        parsed = Message()
        parsed["content-disposition"] = header
        filename = parsed.get_filename()
        return PurePosixPath(filename).suffix if filename else None

    def _suffix_from_content_type(self) -> str | None:
        """The extension the content type maps to, if it maps to one."""
        content_type = self.content_type
        return mimetypes.guess_extension(content_type) if content_type else None

    def _suffix_from_url(self) -> str | None:
        """The extension on the request URL's path, if it has one."""
        return PurePosixPath(self._response.request.url.path).suffix or None

    @property
    def size(self) -> int | None:
        """The size in bytes of the body ``iter_bytes`` and ``save`` deliver.

        Read from ``Content-Length``. ``None`` when the server declares no
        length — because it streams the response chunked, or because it
        compressed the body: ``Content-Length`` then measures the bytes on
        the wire, while the bytes handed to the caller are the decoded ones,
        and reporting the former would be a number describing a different
        body. A size is either true of what you receive or absent.
        """
        if "content-encoding" in self._response.headers:
            return None
        header = self._response.headers.get("content-length")
        if header is None:
            return None
        try:
            return int(header)
        except ValueError:
            return None
