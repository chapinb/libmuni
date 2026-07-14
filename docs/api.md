# API reference

## Client

::: libcivicclerk.CivicClerkClient

## Models

All models are frozen dataclasses. Each keeps the unmodified API payload in
its `raw` attribute, so upstream fields the library does not model yet stay
reachable.

::: libcivicclerk.Event

::: libcivicclerk.EventCategory

::: libcivicclerk.EventLocation

::: libcivicclerk.PublishedFile

::: libcivicclerk.Agenda

::: libcivicclerk.AgendaItem

::: libcivicclerk.AgendaAttachment

## Errors

Everything the library raises subclasses `CivicClerkError`.

::: libcivicclerk.CivicClerkError

::: libcivicclerk.UnknownTenantError

::: libcivicclerk.NotFoundError

::: libcivicclerk.APIStatusError

::: libcivicclerk.NetworkError

::: libcivicclerk.PayloadError
