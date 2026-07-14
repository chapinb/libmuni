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
        The process exit code.
    """
    args = _build_parser().parse_args(argv)
    try:
        with client_factory(args.tenant) as client:
            args.command(client, args)
    except CivicClerkError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
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
        type=int,
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
    text.add_argument("tenant", help="portal subdomain, e.g. exampletown")
    text.add_argument("file_id", type=int, help="published file id")
    text.set_defaults(command=_run_text)

    download = subparsers.add_parser("download", help="download a meeting-level file")
    download.add_argument("tenant", help="portal subdomain, e.g. exampletown")
    download.add_argument("file_id", type=int, help="published file id")
    download.add_argument("destination", type=Path, help="local path to write the file to")
    download.set_defaults(command=_run_download)

    return parser


def _add_common_arguments(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("tenant", help="portal subdomain, e.g. exampletown")
    subparser.add_argument(
        "--json",
        action="store_true",
        help="print raw API payloads instead of formatted text",
    )


def _run_categories(client: CivicClerkClient, args: argparse.Namespace) -> None:
    categories = client.get_event_categories()
    if args.json:
        _print_json([category.raw for category in categories])
        return
    for category in categories:
        print(f"{category.id:>6}  {category.name or '(unnamed)'}")


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
        when = event.starts_at.strftime("%Y-%m-%d %H:%M")
        agenda = f"  agenda:{event.agenda_id}" if event.agenda_id else ""
        print(f"{when}  {event.name or '(untitled)'}{agenda}")


def _run_agenda(client: CivicClerkClient, args: argparse.Namespace) -> None:
    agenda = client.get_agenda(args.agenda_id)
    if args.json:
        _print_json(agenda.raw)
        return

    def render(items: list, depth: int) -> None:
        for item in items:
            count = len(item.attachments)
            suffix = f"  [{count} attachment{'s' if count != 1 else ''}]" if count else ""
            print(f"{'  ' * depth}{item.name or '(untitled)'}{suffix}")
            render(item.children, depth + 1)

    render(agenda.items, 0)


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


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2)
    print()
