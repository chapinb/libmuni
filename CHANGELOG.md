# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial public release: `CivicClerkClient`, a read-only client for one
  tenant's CivicClerk API — meeting categories, lazily paginated events with
  date and category filters, structured agendas, and streaming file and
  attachment downloads.
- Typed model layer (`Event`, `Agenda`, `AgendaItem`, `AgendaAttachment`,
  `EventCategory`, `EventLocation`, `PublishedFile`) as frozen dataclasses,
  each keeping the raw API payload in `.raw`.
- Typed error hierarchy under `CivicClerkError` (`APIStatusError`,
  `UnknownTenantError`, `NotFoundError`, `NetworkError`, `PayloadError`).
- `FileStream` for name-after-headers download workflows, exposing content
  type, extension, and size before the body is read.
- Polite-by-default request pacing (`min_request_interval`) and a `civicclerk`
  demo CLI.

### Security

- Tenant is validated as a single DNS label before any request is made, so a
  crafted value cannot redirect requests off `{tenant}.api.civicclerk.com`.
- Documented that attachment downloads follow an API-supplied URL (server-side
  request forgery surface) and that responses are not size-bounded, so callers
  fetching from untrusted tenants know to isolate the network and cap sizes.

[Unreleased]: https://github.com/chapinb/libcivicclerk/commits/main
