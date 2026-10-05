# telemetry-event-consumer

Reads telemetry events from the [`kafka`](../kafka/) component's `telemetry-events` topic and
writes each one, verbatim, into [`els-database`](../els-database/)'s `events.telemetry_event`
landing table. Third and last part of the generator → Kafka → SQL Server pipeline:
[`telemetry-event-generator`](../telemetry-event-generator/) → [`kafka`](../kafka/) → **this**.

This is a pure sink. It does not parse, validate, or reshape the event payload — it stores exactly
the JSON bytes Kafka delivered (`payload`), stamped with ingestion time (`row_inserted_time`, when
this consumer wrote the row — not event time, which is already inside the payload itself). Any
parsing or typing of individual event fields is left to whatever reads `events.telemetry_event`
next.

## Setup

This needs the `events` schema already deployed in `els-database` — specifically
`migrations/events/V0001__initial_schema.sql` (the table itself) and
`migrations/events/V0002__telemetry_consumer_login.sql` / `R__01_grant_telemetry_consumer.sql`
(the least-privilege SQL login this component connects as). See
[`els-database`'s README](../els-database/README.md) for running migrations, and that component's
`migrations/events/` folder for the exact login name and the one-time `-Placeholders` step needed
to create it without committing its password anywhere.

Unlike this pipeline's other two components, **this one only runs inside Docker** — there's no
"install Python and the ODBC driver locally" path, because the Dockerfile already does that once,
in version control, rather than leaving it as a README step someone has to remember to repeat.
You need Docker Desktop (already set up for the [`kafka`](../kafka/) component) and nothing else.

1. Bring `kafka` up first, if it isn't already: `docker compose -f ../kafka/docker-compose.yml up -d`
   — this component's `docker-compose.yml` joins `kafka`'s Docker network (`els-kafka-net`), which
   has to already exist.
2. Copy `config/config.template.json` to `config/config.json` and fill in real values: the SQL
   login's real password, and (if different from the defaults) your SQL Server host/database. The
   template's `sqlServer.host` is `host.docker.internal`, not `localhost` — see "Known gotchas"
   below for why that matters.
3. `docker compose up -d --build`

`config/config.json` is bind-mounted into the container read-only, not copied into the image, so a
real password never ends up baked into an image layer (see `Dockerfile`'s own comment on this).

## Running tests

The test suite needs neither a live Kafka broker nor a live SQL Server — it runs against hand-written
fakes for both, so it works offline, anywhere:

```bash
pip install -r requirements-dev.txt
pytest
```

This mirrors `telemetry-event-generator`'s testing setup (`tests/`, `conftest.py`, `pytest.ini`,
`requirements-dev.txt`) — see that component's `CLAUDE.md` for the reasoning, which isn't repeated
here since it's meant to be a repo-wide convention, not something to re-justify per component.

## Known gotchas

- **`host.docker.internal`, not `localhost`, to reach SQL Server from inside the container.**
  SQL Server runs natively on the Windows host, not in Docker — from inside a container,
  `localhost` means the container itself, not the host machine. `host.docker.internal` is Docker
  Desktop's special DNS name for reaching the host. This is a different gotcha from the `kafka`
  component's dual-listener one, but the same underlying lesson: a container's view of "where is
  the other side of this connection" is never automatically the same as the host's.
- **`broker:19092`, not `localhost:9092`, for Kafka.** This consumer runs on the same Docker
  network as the broker, so it uses the internal listener — the opposite choice from
  `telemetry-event-generator`, which runs natively on the host and uses `localhost:9092`. Same
  broker, two different addresses, depending on which side of the Docker network boundary the
  client is on (see `kafka/CLAUDE.md`'s two-listener explanation).
- **At-least-once delivery; duplicate rows are possible if the container crashes between a
  successful database write and committing that message's Kafka offset.** `events.telemetry_event`
  has no column tying a row back to its Kafka origin (no partition/offset), so a duplicate from
  this can't be detected or deduped after the fact. This is a known, deliberately accepted trade-off
  for now, not an oversight — see `CLAUDE.md`.
