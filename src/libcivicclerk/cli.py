"""The ``civicclerk`` demo command.

A thin argparse front-end over ``CivicClerkClient`` that demonstrates the
library's capabilities against any tenant — each subcommand mirrors one
client method, and ``--json`` prints the raw API payloads that every model
keeps in its ``raw`` attribute. Exit codes: 0 on success, 1 when the
library raises a ``CivicClerkError``, 2 for usage errors (argparse).
"""

import argparse
import datetime as dt
import itertools
import json
import sys
from collections.abc import Callable
from pathlib import Path

from libcivicclerk import CivicClerkClient
from libcivicclerk.errors import CivicClerkError

ClientFactory = Callable[[str], CivicClerkClient]


def main(argv: list[str] | None = None, *, client_factory: ClientFactory = CivicClerkClient) -> int:
    """Run the ``civicclerk`` command.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).
        client_factory: Builds the client for a tenant — injectable so
            tests can supply mock transports.

    Returns:
        The process exit code: 0 on success, 1 for a ``CivicClerkError``
        or an ``OSError`` writing output (one line on stderr, no
        traceback), 130 on Ctrl-C. Argparse exits the process with 2 on
        usage errors before this returns.
    """
    args = _build_parser().parse_args(argv)
    try:
        with client_factory(args.tenant) as client:
            args.command(client, args)
    except BrokenPipeError:
        # The reader closed the pipe (e.g. `| head`) — expected, not noisy.
        return 1
    except (CivicClerkError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="civicclerk",
        description=(
            "Explore a CivicClerk meeting portal from the command line. "
            "The tenant is the portal subdomain — the 'exampletown' in "
            "exampletown.portal.civicclerk.com."
        ),
    )
    subparsers = parser.add_subparsers(required=True, metavar="command")

    categories = subparsers.add_parser("categories", help="list the tenant's boards and committees")
    _add_common_arguments(categories)
    categories.set_defaults(command=_run_categories)

    events = subparsers.add_parser("events", help="list meetings, oldest first")
    _add_common_arguments(events)
    events.add_argument(
        "--category", type=int, metavar="ID", help="only this board/committee (see categories)"
    )
    events.add_argument(
        "--from",
        dest="from_date",
        type=dt.date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="only meetings on or after this date",
    )
    events.add_argument(
        "--to",
        dest="to_date",
        type=dt.date.fromisoformat,
        metavar="YYYY-MM-DD",
        help="only meetings on or before this date",
    )
    events.add_argument(
        "--limit",
        type=_nonnegative_int,
        default=15,
        metavar="N",
        help="print at most N meetings; 0 means everything (default: 15, one API page)",
    )
    events.set_defaults(command=_run_events)

    agenda = subparsers.add_parser("agenda", help="show a meeting's structured agenda tree")
    _add_common_arguments(agenda)
    agenda.add_argument("agenda_id", type=int, help="agenda id (shown in events output)")
    agenda.set_defaults(command=_run_agenda)

    text = subparsers.add_parser(
        "text", help="print the API's best-effort text extraction of a file"
    )
    _add_tenant(text)
    text.add_argument("file_id", type=int, help="published file id")
    text.set_defaults(command=_run_text)

    download = subparsers.add_parser("download", help="download a meeting-level file")
    _add_tenant(download)
    download.add_argument("file_id", type=int, help="published file id")
    download.add_argument("destination", type=Path, help="local path to write the file to")
    download.set_defaults(command=_run_download)

    demo = subparsers.add_parser(
        "demo", help="narrated tour of the library surface against a tenant"
    )
    _add_tenant(demo)
    demo.set_defaults(command=_run_demo)

    return parser


def _nonnegative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return number


def _add_tenant(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("tenant", help="portal subdomain, e.g. exampletown")


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    _add_tenant(subparser)
    subparser.add_argument(
        "--json",
        action="store_true",
        help="print raw API payloads instead of formatted text",
    )


def _format_category(category) -> str:
    return f"{category.id:>6}  {category.name or '(unnamed)'}"


def _format_event(event) -> str:
    agenda = f"  agenda:{event.agenda_id}" if event.agenda_id else ""
    return f"{event.starts_at:%Y-%m-%d %H:%M}  {event.name or '(untitled)'}{agenda}"


def _run_categories(client: CivicClerkClient, args: argparse.Namespace) -> None:
    categories = client.get_event_categories()
    if args.json:
        _print_json([category.raw for category in categories])
        return
    for category in categories:
        print(_format_category(category))


def _run_events(client: CivicClerkClient, args: argparse.Namespace) -> None:
    events = client.iter_events(
        category_id=args.category, from_date=args.from_date, to_date=args.to_date
    )
    if args.limit:
        events = itertools.islice(events, args.limit)
    if args.json:
        _print_json([event.raw for event in events])
        return
    for event in events:
        print(_format_event(event))


def _run_agenda(client: CivicClerkClient, args: argparse.Namespace) -> None:
    agenda = client.get_agenda(args.agenda_id)
    if args.json:
        _print_json(agenda.raw)
        return
    _render_agenda_items(agenda.items, depth=0)


def _render_agenda_items(items: list, depth: int) -> None:
    for item in items:
        count = len(item.attachments)
        suffix = f"  [{count} attachment{'s' if count != 1 else ''}]" if count else ""
        print(f"{'  ' * depth}{item.name or '(untitled)'}{suffix}")
        _render_agenda_items(item.children, depth + 1)


def _run_text(client: CivicClerkClient, args: argparse.Namespace) -> None:
    text = client.get_file_text(args.file_id)
    if text is None:
        # Within the API's contract (best-effort extraction), so not an
        # error exit — but stdout stays clean for piping.
        print(f"no text available for file {args.file_id}", file=sys.stderr)
        return
    print(text)


def _run_download(client: CivicClerkClient, args: argparse.Namespace) -> None:
    destination = client.download_file(args.file_id, args.destination)
    print(f"saved {destination}")


_DEMO_PREVIEW = 5
"""Entries shown per demo step — enough to get the idea."""

_DEMO_SCAN = 15
"""Meetings fetched (one API page): the tour previews 5 but scans deeper
for one with an agenda and one with files, so sparse tenants still get
the full walk."""


def _run_demo(client: CivicClerkClient, args: argparse.Namespace) -> None:
    _step("Boards and committees", "client.get_event_categories()")
    categories = client.get_event_categories()
    for category in categories[:_DEMO_PREVIEW]:
        print(f"  {_format_category(category)}")
    if len(categories) > _DEMO_PREVIEW:
        print(f"  ... and {len(categories) - _DEMO_PREVIEW} more")

    today = dt.date.today()
    from_date = today - dt.timedelta(days=60)
    to_date = today + dt.timedelta(days=60)
    _step(
        "Meetings within 60 days",
        f"client.iter_events(from_date={from_date!r}, to_date={to_date!r})",
    )
    events = list(
        itertools.islice(client.iter_events(from_date=from_date, to_date=to_date), _DEMO_SCAN)
    )
    if not events:
        print("  this tenant has no meetings in the window — try the events subcommand")
        return
    for event in events[:_DEMO_PREVIEW]:
        print(f"  {_format_event(event)}")

    with_agenda = next((event for event in events if event.agenda_id), None)
    if with_agenda is None or with_agenda.agenda_id is None:
        print("\nno published agenda in these meetings — skipping the agenda tour")
    else:
        _step(
            f"Agenda of {with_agenda.name or 'that meeting'}",
            f"client.get_agenda({with_agenda.agenda_id})",
        )
        _render_agenda_items(client.get_agenda(with_agenda.agenda_id).items, depth=1)

    with_files = next((event for event in events if event.published_files), None)
    if with_files is None:
        print("\nno published files in these meetings — skipping text extraction")
    else:
        file = with_files.published_files[0]
        _step(
            f"Text of {file.name or file.file_type or 'a document'}",
            f"client.get_file_text({file.file_id})",
        )
        text = client.get_file_text(file.file_id)
        if text is None:
            print("  (the API returned no text for this file — a best-effort feature)")
        else:
            snippet = text[:300]
            print(f"  {snippet}{'...' if len(text) > 300 else ''}")

    print(
        "\nEvery model keeps the raw API payload in .raw — "
        "try --json on the categories, events, or agenda subcommands to see it."
    )


def _step(title: str, python: str) -> None:
    """Print a demo step heading with its equivalent library call."""
    print(f"\n== {title}")
    print(f">>> {python}")


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2)
    print()
