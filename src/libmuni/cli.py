"""The ``muni`` command: a launcher over libmuni's per-platform CLIs.

``muni`` owns only routing. It selects a platform from its first argument and
hands every remaining argument to that platform's own command-line interface,
which owns its verbs, help text, and error handling. Adding a platform is one
entry in ``_PLATFORMS``; nothing else here needs to change.
"""

import argparse
import sys
from collections.abc import Callable, Sequence
from functools import partial

from libmuni.civicclerk import cli as civicclerk_cli

PlatformCLI = Callable[[list[str] | None], int]
"""A platform CLI: given the arguments after the platform token, run and
return a process exit code."""

_PLATFORMS: dict[str, PlatformCLI] = {
    "civicclerk": partial(civicclerk_cli.main, prog="muni civicclerk"),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``muni`` command.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``). The first item
            selects a platform; the rest are passed through untouched.

    Returns:
        The exit code of the selected platform's CLI. Argparse exits the
        process with 2 on an unknown or missing platform, and 0 after
        printing ``--help``, before this returns.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in _PLATFORMS:
        # No platform, an unknown platform, or a top-level flag such as
        # --help: let argparse render the platform listing or usage error
        # and exit. A recognized platform bypasses this and delegates.
        _build_parser().parse_args(args)
    platform, rest = args[0], args[1:]
    return _PLATFORMS[platform](rest)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="muni",
        description=(
            "Access municipal government data platforms from the command line. "
            "Each platform has its own subcommands — run 'muni <platform> --help'."
        ),
    )
    subparsers = parser.add_subparsers(required=True, metavar="platform")
    for name in _PLATFORMS:
        subparsers.add_parser(name, help=f"query a {name} portal")
    return parser
