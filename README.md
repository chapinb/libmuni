# libcivicclerk

A read-only Python client for the CivicClerk public meeting-portal API.

CivicClerk is a meeting-portal platform used by many municipalities to
publish meeting calendars, agendas, minutes, and supporting documents. Those
portals are backed by a public, unauthenticated API at
`https://{tenant}.api.civicclerk.com/v1`. This library gives developers a
small, typed, well-behaved client for reading that data — meeting calendars,
attendance details, structured agendas, and document downloads — without
reverse-engineering the API themselves.

> **Status:** pre-release; the public surface is still taking shape.

## Install

```sh
pip install libcivicclerk
```

Requires Python 3.11+.

## Quickstart

Coming with the first release — see `docs/specs/` for the roadmap.

## Versioning

Semantic versioning covers **this library's surface only**. The upstream
CivicClerk API is undocumented and makes no compatibility promises; every
model keeps the raw response payload reachable so upstream additions are
usable immediately, and upstream drift is addressed in library releases.

## Disclaimer

This project is not affiliated with, endorsed by, or supported by CivicPlus
or the CivicClerk product. "CivicClerk" is used only to describe the API this
library talks to. The library reads publicly available government records;
please use it politely (modest request rates) and note that any
redistribution of downloaded documents is the responsibility of downstream
applications.

## License

MIT
