# Command line

Installing the package also installs `civicclerk`, a small command that
demonstrates the library against any tenant — every subcommand mirrors one
client method, so the CLI doubles as living documentation. The tenant is
the portal subdomain: the `exampletown` in
`exampletown.portal.civicclerk.com`.

## The guided tour

The quickest way to see what the library does:

```sh
civicclerk demo exampletown
```

It walks the whole surface — boards, recent meetings, an agenda tree, a
document's extracted text — printing the equivalent Python call before
each step.

## Subcommands

```sh
civicclerk categories exampletown            # boards and committees
civicclerk events exampletown --limit 5      # meetings, oldest first
civicclerk events exampletown --category 12 --from 2026-07-01 --to 2026-08-01
civicclerk agenda exampletown 7301           # a meeting's agenda tree
civicclerk text exampletown 9001             # best-effort text extraction
civicclerk download exampletown 9001 packet.pdf
```

`events` prints at most 15 meetings (one API page) unless you raise
`--limit`; `--limit 0` walks the tenant's entire history — paced politely,
so expect a long run on a large portal.

## Raw payloads

`categories`, `events`, and `agenda` accept `--json`, which prints the
unmodified API payloads instead of formatted text — the same data every
model carries in its `raw` attribute:

```sh
civicclerk events exampletown --limit 3 --json | jq '.[0].eventName'
```

## Exit codes

- `0` — success. This includes `text` printing "no text available": the
  API's extraction is best-effort and answers unknown ids the same way,
  so absence is within its contract.
- `1` — a library error (unknown tenant, an id the API reports missing,
  network failure) or a filesystem error writing a download; one line on
  stderr, no traceback.
- `2` — usage error (bad arguments).
- `130` — interrupted with Ctrl-C.
