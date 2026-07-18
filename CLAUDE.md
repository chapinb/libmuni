# libmuni

Read-only Python clients for municipal government software platforms, one
client per platform under the `libmuni` namespace. The first is
`libmuni.civicclerk`, a client for the CivicClerk public meeting-portal API
(`https://{tenant}.api.civicclerk.com/v1`). Each client is thin and typed:
every public method maps to one HTTP request; models are frozen dataclasses
with a `raw` escape hatch. The clients share no cross-vendor data model — the
jurisdiction unifies them, not a schema — and every error subclasses
`libmuni.MuniError`. See `docs/decisions.md` for architecture decisions and
`docs/specs/` for the active spec-as-plan.

## Commands

- `uv sync` — install (uses dev group)
- `uv run pytest` — tests (live suite deselected by default; `-m live` opts in)
- `uv run ruff check` / `uv run ruff format --check` — lint / format
- `uv run ty check` — type check
- `uvx prek run --all-files` — full hook suite (what CI enforces)

## Constraints

- Public repo: no references to any specific municipality or private project
  in code, docs, tests, or examples. Recorded fixtures are scrubbed to
  fictional tenants before commit.
- Public surface must be self-documenting: full type hints, keyword-only
  optional params, docstrings stating units, timezone semantics, and failure
  modes (ruff pydocstyle enforces presence).
- Two-tier parsing: load-bearing fields raise typed payload errors when
  missing; all other fields are best-effort Optional. No pydantic; httpx is
  the only runtime dependency.
- Read-only, unauthenticated API surface only. Callers own retries, caching,
  and rate limiting.

## Changelog and releases

- Keep `CHANGELOG.md` (Keep a Changelog format) current: every `FFF` (feature)
  and `B -` (bug fix) commit adds an entry under `## [Unreleased]`;
  `t -` / `d -` / `R -` / `a -` commits do not require one.
- `pyproject.toml`'s version reflects the last *released* version. Bump it only
  in the release commit, in the same commit that renames `## [Unreleased]` to
  `## [x.y.z] - <date>`. The `changelog-version` hook fails if a released
  changelog heading and the packaged version disagree.
- Release steps: rename `[Unreleased]` to a dated `[x.y.z]` section, add a fresh
  empty `[Unreleased]`, bump the version in `pyproject.toml`, update the compare
  links, commit, then tag `vx.y.z`.
