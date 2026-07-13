# libcivicclerk

Read-only Python client for the CivicClerk public meeting-portal API
(`https://{tenant}.api.civicclerk.com/v1`). Thin typed client: every public
method maps to one HTTP request; models are frozen dataclasses with a `raw`
escape hatch. See `docs/decisions.md` for architecture decisions and
`docs/specs/` for the active spec-as-plan.

## Commands

- `uv sync` — install (uses dev group)
- `uv run pytest` — tests (live suite deselected by default; `-m live` opts in)
- `uv run ruff check` / `uv run ruff format --check` — lint / format
- `uv run ty check` — type check
- `prek run --all-files` — full hook suite (what CI enforces)

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
