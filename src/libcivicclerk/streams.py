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

import httpx


class FileStream:
    """A file's response headers and body, open and not yet consumed.

    Obtained from ``CivicClerkClient.open_file`` or ``open_attachment``,
    and valid only inside their ``with`` block — the response closes on
    exit.

    Args:
        response: The open, streaming response to wrap.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

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
