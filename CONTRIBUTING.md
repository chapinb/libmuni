# Contributing

Thanks for your interest. Bug reports, documentation fixes, and pull requests
are all welcome — this library exists to make public meeting records easier to
work with, and that gets better with more eyes on it.

## Getting started

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync                  # install, with dev tools
uv run pytest            # tests (the live suite is excluded by default)
prek run --all-files     # lint, format, type check — exactly what CI enforces
```

A clean `prek run --all-files` means a clean CI run, so run it before you push
and you should not be surprised.

## Reporting a bug

Open an issue at
[github.com/chapinb/libmuni/issues](https://github.com/chapinb/libmuni/issues).

If parsing broke, the single most useful thing you can include is **the payload
that broke it** — every model keeps the raw response reachable via `.raw`, so
you can capture it directly. Please scrub it of anything that identifies a
specific municipality before posting (see the constraint below).

## Things that will get a pull request sent back

These are deliberate design constraints, not preferences. Knowing them up front
is kinder than discovering them in review.

- **No specific municipality anywhere.** Not in code, docs, tests, examples, or
  fixtures. Recorded fixtures are scrubbed to fictional tenants before they are
  committed. The library is tenant-generic by construction.
- **Two-tier parsing.** A small set of load-bearing fields raise a typed
  `PayloadError` when they are missing or malformed. Every other field is
  best-effort `Optional` — absent optional data is never an error. Do not
  promote a field to load-bearing without a reason.
- **httpx is the only runtime dependency.** New runtime dependencies are a hard
  sell; no pydantic.
- **Read-only and unauthenticated.** No writes, no credentials, no auth
  parameters.
- **The public surface documents itself.** Full type hints, keyword-only
  optional parameters, and docstrings that state units, timezone semantics, and
  failure modes. Ruff's pydocstyle rules enforce that the docstrings exist; you
  are on the hook for them being true.

## Changelog

Feature (`FFF`) and bug-fix (`B -`) changes add an entry under `## [Unreleased]`
in `CHANGELOG.md`. Documentation, test, and refactor-only changes do not need
one. A hook checks that the packaged version and the changelog agree, so this is
enforced rather than remembered.

## The live suite

There is an opt-in suite of contract tests that run against a real CivicClerk
tenant, used to detect upstream API drift. It is deselected by default:

```sh
CIVICCLERK_TEST_TENANT=<tenant> uv run pytest -m live
```

Point it at any tenant you like. **You are not expected to run it** to
contribute — CI covers it on a schedule.

## Design decisions

`docs/decisions.md` records why the library is shaped the way it is — the thin
client, the lenient parsing, the naive datetimes, the caller-owned retries.
Please read it before proposing an architectural change. If you think one of
those decisions is wrong, say so and point at it directly; they are arguments,
not commandments.

## License

By contributing, you agree that your contributions are licensed under the
project's [MIT license](LICENSE). There is no CLA and no DCO sign-off to worry
about.
