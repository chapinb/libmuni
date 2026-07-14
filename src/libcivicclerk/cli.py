"""The ``civicclerk`` demo command.

A thin argparse front-end over ``CivicClerkClient`` that demonstrates the
library's capabilities against any tenant — each subcommand mirrors one
client method, and ``--json`` prints the raw API payloads that every model
keeps in its ``raw`` attribute. Exit codes: 0 on success, 1 when the
library raises a ``CivicClerkError``, 2 for usage errors (argparse).
"""

import argparse
import json
import sys
from collections.abc import Callable

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


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, indent=2)
    print()
