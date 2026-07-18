# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-18

### Added

- Initial public release: `libmuni`, read-only clients for municipal
  government software platforms. The first platform is `libmuni.civicclerk`,
  a client for one tenant's CivicClerk meeting API — meeting categories,
  lazily paginated events with date and category filters, structured agendas,
  and streaming file and attachment downloads.
- Typed model layer (`Event`, `Agenda`, `AgendaItem`, `AgendaAttachment`,
  `EventCategory`, `EventLocation`, `PublishedFile`) as frozen dataclasses,
  each keeping the raw API payload in `.raw`.
- `MuniError` as the root of every operational error the library raises; each
  platform's hierarchy descends from it (`CivicClerkError` and its
  `APIStatusError`, `UnknownTenantError`, `NotFoundError`, `NetworkError`,
  `PayloadError`), so a caller spanning platforms can catch them all with one
  `except`. Invalid arguments raise `ValueError` and local file writes raise
  `OSError`, standard built-ins left outside the hierarchy.
- `FileStream` for name-after-headers download workflows, exposing content
  type, extension, and size before the body is read.
- Polite-by-default request pacing (`min_request_interval`) and a `muni-cli`
  command-line interface that routes to per-platform subcommands
  (`muni-cli civicclerk ...`).

### Security

- Tenant is validated as a single DNS label before any request is made, so a
  crafted value cannot redirect requests off `{tenant}.api.civicclerk.com`.
- Documented that attachment downloads follow an API-supplied URL (server-side
  request forgery surface), as do pagination continuation links and redirects,
  and that responses are not size-bounded, so callers fetching from untrusted
  tenants know to isolate the network and cap sizes.
- Exception diagnostics redact URL credentials, query strings, and fragments
  so signed download URLs and continuation tokens do not enter routine logs.

[Unreleased]: https://github.com/chapinb/libmuni/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/chapinb/libmuni/releases/tag/v0.1.0
