# Download streams: let the caller see the response before naming the file

## Goal

A caller who downloads a meeting file or an agenda attachment has to choose
a destination path before the request is made, but the only authoritative
source for the file's type is the response — and today the client swallows
the response and hands back the `Path` the caller already supplied. The
result is that every caller hardcodes `.pdf` and is silently wrong the day a
tenant publishes something else.

A live probe settled where the naming information actually lives. Meeting
file streams answer with `content-type: application/pdf` and
`content-disposition: attachment; filename=<file_id>.pdf` — the filename is
the numeric id restated, not a human name. Agenda attachments are blobs on a
different host with no `content-disposition` at all and a GUID URL path
ending in `.pdf`. Neither response carries a name worth using. The human name
is already in the models (`PublishedFile.name`, `AgendaAttachment.file_name`)
and has no extension.

So the caller owns the name and the response owns the extension, and the two
never meet. `HEAD` answers 405, so there is no way to ask ahead of time. This
work exposes the response — content type, extension, size, and the raw byte
stream — at the one moment it is useful: after the headers arrive and before
the body is consumed.

## Requirements

- A caller can learn a file's content type, extension, and (when the server
  sends `Content-Length`) its size before deciding where to write it.
- A caller can consume the bytes without touching the disk — streaming a file
  into a parser or an object store must not require a temporary file.
- The extension is derived from the response, not guessed, and is `None` when
  the response gives no basis for one rather than defaulting to `.pdf`.
- Saving to an explicit path writes exactly that path — the library never
  renames, appends to, or otherwise edits a destination the caller chose.
- The existing "HTTP 200 with a 0-byte body means unavailable" trap still
  raises `NotFoundError`, and still cannot leave a partial or empty file on
  disk. It must surface when the stream is opened, not partway through
  iteration, so a caller cannot silently write a 0-byte PDF.
- `download_file` and `download_attachment` keep their current signatures and
  behavior exactly; existing callers see no change.

## Out of scope

- Any change to `get_file_text` or the plain-text extraction endpoint.
- Async streaming. The client is synchronous; that is settled.
- Resumable or ranged downloads. The meeting-file endpoint ignores `Range`.
  (The attachment blob host does advertise `accept-ranges: bytes`, which is
  noted under Deferred, not built here.)
- Content sniffing. If the response provides no type, we report none — we do
  not inspect magic bytes.
- Any caching, retry, or concurrency policy. That stays caller-owned.

## Constraints

**Public surface sketch.** Two new client methods, each a context manager and
each performing exactly one HTTP request, consistent with the one-method
one-request rule:

- `open_file(file_id: int)` — yields a stream for a meeting-level file,
  mirroring `download_file`'s id semantics and its `NotFoundError` behavior.
- `open_attachment(attachment: AgendaAttachment)` — yields a stream for an
  agenda attachment, raising the same `ValueError` as `download_attachment`
  when `download_url` is `None`.

Both yield a `FileStream`, a new public type exported from the package root,
exposing: `content_type: str | None` (the response media type, parameters
stripped); `suffix: str | None` (the leading-dot extension, or `None` when
undeterminable); `size: int | None` (`Content-Length`, `None` when the server
streams chunked); `iter_bytes()` (an iterator of non-empty chunks); and
`save(destination: Path) -> Path` (writes the body to exactly `destination`
and returns it).

`FileStream` is not a frozen dataclass — it wraps a live response and is the
one mutable, lifetime-bound object in the public surface.

**save() writes verbatim.** A destination with no extension is written with
no extension. The caller composes the filename from the model's name and the
stream's `suffix`, both of which are in scope inside the `with` block. The
library never edits the path it was handed.

**Suffix derivation differs per endpoint** and must be ordered, not
per-method: the `filename` in `Content-Disposition` when present (correct for
meeting files, whose id-based filename still carries a truthful extension),
then `mimetypes.guess_extension` on the content type, then the suffix of the
request URL's path (which is what rescues attachments, whose GUID blob paths
end in a real extension). `None` when all three yield nothing.

**Empty-body detection happens on entry.** `Content-Length: 0` is decisive.
When the header is absent, the stream must read the first chunk before
yielding to the caller and raise `NotFoundError` if there is none. That
buffered chunk has to be replayed as the first chunk of `iter_bytes()`, or
the body is silently truncated — this is the sharpest edge in the work and
the one a test must pin.

**No partial files.** `save` must not leave a file at `destination` if the
write fails; the existing unlink-on-failure guarantee in `_stream_to_file`
is the behavior to preserve.

**Lifetime is the `with` block.** The response closes on exit; `iter_bytes`
and `save` are invalid afterward and must say so in their docstrings.

**Pacing applies once per opened stream**, as it does today for every request
funnel.

Standard project constraints hold: full type hints, keyword-only optional
params, docstrings stating units and failure modes, `httpx` as the only
runtime dependency (`mimetypes` is stdlib), no municipality named anywhere.

## Environment

- `uv run pytest` — tests (live suite deselected; `-m live` opts in, and needs
  `CIVICCLERK_TEST_TENANT` set)
- `uv run ruff check` / `uv run ruff format --check` — lint / format
- `uv run ty check` — type check
- `prek run --all-files` — full hook suite (what CI enforces)

## Decision log

- **Context manager over a richer return type or path-mutating downloads.**
  Both alternatives force the naming decision before the information exists: a
  `Download` result object means downloading to a temp path and renaming
  afterward, and a directory-valued `destination` would write the server's
  filename — which the probe showed is `<file_id>.pdf` or a GUID, strictly
  worse than what the caller already has. A context manager hands over the
  headers at the only moment they are actionable: after they arrive, before
  the body is read.
- **`save()` writes verbatim rather than appending a missing suffix.** The
  suffix is in scope inside the `with` block, so auto-appending buys one
  string interpolation while making the return value diverge from the
  argument and making an intentionally extensionless file impossible.
- **`download_file` / `download_attachment` are retained**, reimplemented on
  the context manager. They are the right one-liner for "I already know the
  name I want"; removing them would be a breaking change that buys nothing.

## Deferred

- The attachment blob host advertises `accept-ranges: bytes`, so attachment
  downloads (unlike meeting files) could be resumed. Not built; revisit if
  large-packet downloads prove flaky.
- `download_file` takes a bare `int` while `download_attachment` takes a
  model, so `download_file` cannot see `PublishedFile.name` even to offer a
  fallback. Accepting `PublishedFile | int` would settle the asymmetry.

## Done criteria

- A caller can open a meeting file or an attachment, read its content type,
  extension, and size, and either save it under a name of their own
  composition or consume its bytes without writing to disk.
- An unavailable file (empty 200 body) raises `NotFoundError` at the point the
  stream is opened, and leaves nothing on disk.
- A chunked response with no `Content-Length` yields all of its bytes,
  including the first chunk that entry-time detection had to read.
- `download_file` and `download_attachment` behave exactly as before, with
  their existing tests untouched and green.
- `FileStream` is exported, documented in `usage.md` and `cheatsheet.md`, and
  the reasoning is recorded in `docs/decisions.md`.
- `prek run --all-files` passes.

## Slices

- [x] **Tracer bullet** — `FileStream` wrapping a live response and
  `client.open_file(file_id)` yielding it, exposing `content_type` and `size`
  only. Acceptance: a mock transport serving a PDF with known headers yields a
  stream reporting `application/pdf` and its length. Touches `client.py`, new
  `streams.py`, `tests/test_downloads.py`.
- [x] **Empty-body detection on entry** — `Content-Length: 0` and, when the
  header is absent, an empty first chunk both raise `NotFoundError` from the
  `with` statement itself. Acceptance: entering the stream for an empty 200
  raises before any body is read, and no file is created. Touches `streams.py`.
- [ ] **`iter_bytes()` replaying the peeked chunk** — a chunked response with
  no `Content-Length` yields every byte, first chunk included. Acceptance:
  bytes collected from `iter_bytes` equal the full body for both
  `Content-Length` and chunked responses. Touches `streams.py`.
- [ ] **`suffix`** — ordered derivation from `Content-Disposition` filename,
  then content type, then URL path; `None` when all fail. Acceptance: a
  meeting-file response resolves `.pdf` from its `filename=<id>.pdf`, an
  attachment-shaped response with only a GUID `.pdf` URL and a content type
  also resolves `.pdf`, and a typeless response resolves `None`. Touches
  `streams.py`.
- [ ] **`save(destination)`** — writes exactly the path given, returns it, and
  leaves nothing behind on failure. Acceptance: an extensionless destination
  stays extensionless; a mid-stream transport failure leaves no file. Touches
  `streams.py`.
- [ ] **`open_attachment(attachment)`** — mirrors `open_file` for signed blob
  URLs, raising `ValueError` when `download_url` is `None`. Acceptance: a link
  attachment raises `ValueError`; a file attachment streams. Touches
  `client.py`.
- [ ] **Reimplement `download_file` / `download_attachment` on the context
  managers**, retiring `_stream_to_file`. Acceptance: the existing download
  tests pass unchanged. Touches `client.py`.
- [ ] **Export and document** — `FileStream` in `__all__`, a streaming section
  in `usage.md`, the new methods in `cheatsheet.md`, an ADR entry in
  `docs/decisions.md`, and a live contract test asserting a real published file
  reports a content type. Touches `__init__.py`, `docs/`, `tests/test_live.py`.
