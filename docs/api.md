# API reference

## Client

::: libmuni.civicclerk.CivicClerkClient

## Models

All models are frozen dataclasses. Each keeps the unmodified API payload in
its `raw` attribute, so upstream fields the library does not model yet stay
reachable.

::: libmuni.civicclerk.Event

::: libmuni.civicclerk.EventCategory

::: libmuni.civicclerk.EventLocation

::: libmuni.civicclerk.PublishedFile

::: libmuni.civicclerk.Agenda

::: libmuni.civicclerk.AgendaItem

::: libmuni.civicclerk.AgendaAttachment

## Errors

Every error any libmuni client raises subclasses `MuniError`. The CivicClerk
client's errors subclass `CivicClerkError`, which in turn subclasses
`MuniError`, so a caller spanning platforms can catch them all at once.

::: libmuni.MuniError

::: libmuni.civicclerk.CivicClerkError

::: libmuni.civicclerk.UnknownTenantError

::: libmuni.civicclerk.NotFoundError

::: libmuni.civicclerk.APIStatusError

::: libmuni.civicclerk.NetworkError

::: libmuni.civicclerk.PayloadError
