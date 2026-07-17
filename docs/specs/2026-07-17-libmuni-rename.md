# Rename to libmuni and restructure as a multi-platform namespace

## Goal

`libcivicclerk` is a single-vendor client, but a municipality's public record
is spread across several vendors: Norwalk CT alone uses CivicClerk for
meetings, Municode for the charter and ordinances, and CivicPlus for the city
site. Rename the distribution to `libmuni` and move the existing client under
a `libmuni.civicclerk` namespace so later vendors are additive rather than a
second rename. The library stays tenant- and municipality-generic; no CT- or
Norwalk-specific behavior enters the code.

The rename is free right now and expensive later: `libcivicclerk` was never
tagged and is not on PyPI (only a local wheel in `dist/`), so there are no
users to break, no deprecation shim, and no redirect package.

## Requirements

- The distribution is named `libmuni` and `import libmuni.civicclerk` resolves.
- Every public name that `libcivicclerk` exported is reachable under
  `libmuni.civicclerk` with unchanged behavior.
- `MuniError` is the root of the exception hierarchy; `CivicClerkError`
  subclasses it and still catches everything it catches today.
- Requests carry a `libmuni/{version}` User-Agent pointing at the new
  repository URL.
- The CLI is a single `muni` command with a `civicclerk` platform subcommand
  layer (`muni civicclerk events ...`), leaving room for `muni municode ...`.
- `CHANGELOG.md` records no released version; the phantom `[0.1.0]` section is
  folded back into `[Unreleased]`.
- No reference to `libcivicclerk` survives outside `docs/specs/` history.

## Out of scope

- Writing the Municode or CivicPlus clients. This pass moves what exists.
- Extracting a shared HTTP/streaming/parsing core (`libmuni/core/`). Deferred
  by decision until a second client reveals the real seam.
- Any cross-vendor domain model or normalization layer.
- Emitting Open Civic Data, or adopting OCD division IDs as a jurisdiction key.
- Contributing a mixin to `city-scrapers-core` or replying to civic-scraper
  issue #192.
- Creating the GitHub org/repo, publishing to PyPI, tagging a release, or
  standing up `openmunidata.com`. The repo has no git remote; that is a
  maintainer action outside this work.
- Renaming the local working directory.

## Constraints

- The move in slice 1 is atomic and cannot be split. `uv_build` derives the
  package directory from the project name, and `__version__` resolves through
  `importlib.metadata.version("libcivicclerk")`, so the directory move, the
  `pyproject` name, the `__init__` lookup, and the User-Agent string all break
  together the moment any one of them changes.
- The User-Agent is asserted verbatim in `tests/test_user_agent.py`, and
  `tests/test_package.py` asserts the distribution name; both move in slice 1.
- Folding `[0.1.0]` into `[Unreleased]` while `pyproject` stays at `0.1.0`
  passes the `changelog-version` hook — `test_pre_first_release_passes_with_unreleased_section`
  already covers exactly this state. Do not bump the version; `0.1.0` becomes
  libmuni's first real tag later.
- The `muni` dispatcher lives at `src/libmuni/cli.py` and delegates to a
  per-vendor subparser in `src/libmuni/civicclerk/cli.py`. A CLI entry point is
  not the deferred shared core; do not let it grow into one.
- Existing ADRs stand. The "Thin typed client" entry says "v1 exposes one
  client class" — scope that phrasing to one client class per platform; do not
  rewrite the decision.
- Public-surface rules from `CLAUDE.md` continue to bind: full type hints,
  keyword-only optional params, docstrings stating units, timezone semantics,
  and failure modes.
- Repository URL for the User-Agent and `project.urls`:
  `https://github.com/openmunidata/libmuni`. Docs URL moves off
  `chapinb.com/libcivicclerk`.

## Environment

- `uv sync` — install (dev group)
- `uv run pytest` — tests (live suite deselected by default; `-m live` opts in)
- `uv run ruff check` / `uv run ruff format --check` — lint / format
- `uv run ty check` — type check
- `prek run --all-files` — full hook suite (what CI enforces)

## Decision log

- **Move + exception root, not a full core extraction.** `MuniError` is free
  now and a breaking change after first publish; everything else that looks
  shared is generic only against a sample size of one. Recorded in
  `docs/decisions.md`.
- **One package, many vendor clients, no cross-vendor model.** The jurisdiction
  unifies the vendors, not a schema. Recorded in `docs/decisions.md`.
- **`muni civicclerk <verb>` over keeping a bare `civicclerk` command.** One
  command to learn, and `muni municode ...` needs no second entry point.
- **Fold the phantom `[0.1.0]`.** It was never tagged or published, and the
  name it claims will never exist on PyPI.
- **Name.** `libmuni` over `openmunidata`/`libopenmunidata`: the org and domain
  carry the brand, the package stays short and importable. "Data" would
  misdescribe an access layer and re-promise the normalization this library
  declines to do.
- **`__version__` lives at `libmuni`, not `libmuni.civicclerk`** (slice 1).
  The requirement that every exported name reach `libmuni.civicclerk` has this
  one exception: the version describes the distribution, and exposing it per
  vendor would imply per-vendor release cadences that do not exist.
- **`py.typed` moved to `src/libmuni/`** (slice 1). PEP 561 places the marker
  in the top-level package; left inside `civicclerk/` it would not mark the
  distribution as typed.
- **`[project.urls]` deferred to slice 5** (slice 1). The User-Agent's repo URL
  changes in slice 1 because it is asserted by a moving test; the metadata URLs
  are prose-adjacent and travel with the docs pass, leaving them briefly
  inconsistent with the User-Agent.

## Deferred

- Municode and CivicPlus clients.
- Shared core extraction, revisited when client #2 lands.
- OCD division IDs as the jurisdiction key, and a `to_ocd_event()` exporter
  taking an explicit timezone argument.
- A `civicclerk` mixin for `city-scrapers-core` that delegates to this library;
  City Bureau currently has the same CivicClerk API reimplemented across at
  least five per-city repos with nothing shared in core. Open an issue there
  before investing in a PR — their oldest outside platform-mixin PR has sat
  unmerged since June 2024.
- Replying to civic-scraper issue #192, whose CivicClerk support has been
  unmaintained since 2022.

## Done criteria

- `uv run pytest` is green and `prek run --all-files` passes.
- `import libmuni.civicclerk` works from a built wheel; `import libcivicclerk`
  is gone.
- `muni civicclerk --help` lists the existing verbs and `muni --help` lists
  `civicclerk` as a platform.
- Catching `libmuni.MuniError` catches a CivicClerk `NotFoundError`.
- Grepping the repo for `libcivicclerk` outside `docs/specs/` returns nothing.
- `CHANGELOG.md` has an `[Unreleased]` section and no released heading.

## Slices

1. [x] **Tracer: move and rename.** `import libmuni.civicclerk` resolves and the
   full suite is green — move `src/libcivicclerk/` to `src/libmuni/civicclerk/`,
   rename the distribution, repoint internal and test imports, and update the
   User-Agent to `libmuni/{version}` with the new repo URL. Atomic by
   necessity. Touches `src/`, `pyproject.toml`, all nine test modules.
2. **Exception root.** `except libmuni.MuniError` catches a CivicClerk
   `NotFoundError`, and `CivicClerkError` still catches what it did — add
   `src/libmuni/errors.py`, reparent the vendor hierarchy, export from
   `src/libmuni/__init__.py`. Touches `src/libmuni/errors.py` (new),
   `src/libmuni/civicclerk/errors.py`, `tests/test_errors.py`.
3. **CLI dispatcher.** `muni civicclerk events --tenant exampletown` produces
   what `civicclerk events` produced, and `muni --help` lists `civicclerk` —
   add a `muni` dispatcher delegating to the vendor subparser, repoint
   `[project.scripts]`. Touches `src/libmuni/cli.py` (new),
   `src/libmuni/civicclerk/cli.py`, `pyproject.toml`, `tests/test_cli.py`.
4. **Changelog.** `check_changelog_version` passes at `0.1.0` with only an
   `[Unreleased]` section — fold the phantom `[0.1.0]` entries back, drop the
   dated heading, fix compare links. Touches `CHANGELOG.md`.
5. **Docs and metadata.** No `libcivicclerk` outside `docs/specs/`, and the
   docs site builds — update prose, nav, URLs, and the thin-client ADR's "one
   client class" phrasing. Touches `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`,
   `docs/*.md`, `docs/decisions.md`, `mkdocs.yml`, `pyproject.toml` urls.
6. **Stale build artifacts.** `dist/` carries no `libcivicclerk` wheel or
   sdist. Touches `dist/`.
