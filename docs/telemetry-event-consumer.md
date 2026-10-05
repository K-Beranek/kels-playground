# Review: Telemetry Event Consumer (`telemetry-event-consumer`)

## What it is

A Python script that consumes the [`kafka`](../kafka/) component's `telemetry-events` topic and
writes each message, unparsed, into [`els-database`](../els-database/)'s new
`events.telemetry_event` landing table. Third and last part of the pipeline:
[`telemetry-event-generator`](../telemetry-event-generator/) → [`kafka`](../kafka/) → **this**.
The pipeline is now end-to-end, at least in design — see Status for what's actually been run live.

It is a pure sink: `payload` stores the exact JSON bytes Kafka delivered, and
`row_inserted_time` is ingestion time (stamped by SQL Server at insert time), not event time —
the event's own timestamp is already inside `payload`. No parsing, validation, or reshaping of
individual event fields happens here; that's left to whatever reads `events.telemetry_event` next.

## Key decisions

- **Python + `kafka-python`, the same library as the producer — a genuine choice among several,
  not a default.** `confluent-kafka` (a deliberate library fork to compare against
  `kafka-python`'s known rough edges) and C# + `Confluent.Kafka` (new-language practice, a natural
  "redundant implementation" twin) were both raised explicitly and both remain open future work.
  A fourth option, Kafka Connect with a JDBC sink connector (no custom code at all — arguably the
  more realistic production answer), was raised and set aside since the point here is consumer-API
  practice, not connector configuration.
- **Runs as a continuous process in Docker, not a scheduled batch job.** The alternative — start,
  drain what's available, write it, exit, invoked on a schedule — was raised as a real option
  (and a plausible dedicated-Jenkins exercise), but the continuous model is the idiomatic way to
  consume from Kafka: `for message in consumer:` blocks forever by design, and
  `docker-compose.yml`'s `restart: unless-stopped` is the process supervisor, not an external
  scheduler.
- **Its own component, its own `docker-compose.yml`, joining `kafka`'s network from outside.**
  `kafka/CLAUDE.md` is explicit that no application code lives in that component — so this had to
  be a separate component, and `kafka`'s previously-implicit default Docker network was given a
  stable explicit name (`els-kafka-net`) specifically so this component's compose file has
  something reliable to join (`external: true`), independent of folder naming or invocation
  directory.
- **`host.docker.internal` for SQL Server, `broker:19092` for Kafka — two different addressing
  gotchas, same underlying lesson.** SQL Server runs natively on the Windows host, not in Docker,
  so `localhost` from inside this container would mean the container itself; Kafka's broker is
  reached via its internal Docker-network listener instead of the host-facing one the generator
  uses, since this consumer runs on the same Docker network as the broker.
- **Least-privilege SQL login, the first of its kind in this repo.** Every other component
  connects as `els_accountadmin` (effectively an admin account). This consumer connects as a new,
  narrowly-scoped `telemetry_consumer` login, granted `INSERT` on `events.telemetry_event`
  specifically — not the whole `events` schema, on the reasoning that it has no business touching
  any future additional landing table there. Creating that login without committing its password
  introduced Flyway placeholders to this repo (`${telemetry_consumer_password}`, supplied via a
  new `-Placeholders` parameter on `Invoke-ElsMigration.ps1`) — a different, migration-appropriate
  answer to "never commit a secret" than the "commit a template, gitignore the real file" pattern
  used everywhere else, since a migration is meant to be identical SQL for every environment, not
  something with a gitignored real copy.
- **At-least-once delivery; duplicate rows on crash are a known, accepted gap, not solved here.**
  If this container crashes after a database write commits but before that message's Kafka offset
  is committed, the message is redelivered and reinserted on restart. Adding
  `kafka_partition`/`kafka_offset` columns with a unique constraint (making the insert naturally
  idempotent) was raised explicitly and set aside in favor of leaving the table as-is — a real,
  open gap worth revisiting before anything serious is built on top of this table, not an
  oversight.
- **Offsets committed manually, after the database write succeeds — and a database write failure
  stops the process immediately, with no retry.** Kafka's auto-commit default would mark a message
  done before this consumer knows the write actually succeeded, risking silently losing events
  rather than merely risking the accepted duplicate-on-crash case above. Failing loud and exiting
  on a write error is a deliberate synergy with the continuous-Docker-process choice: under
  `restart: unless-stopped`, the container simply restarts and resumes from the last committed
  offset, with no separate retry logic needed in the script itself.

## How other components should use this

- Consumes [`kafka`](../kafka/)'s `telemetry-events` topic — the second and last reader of that
  topic to exist (alongside `kafka-ui`, which only inspects it).
- Writes into [`els-database`](../els-database/)'s new `events` schema — the first component to
  *write* into `els-database` rather than only read from it (`els_transform` and
  `telemetry-event-generator` are both read-only consumers of the `els` schema).
- A future consumer of `events.telemetry_event` (e.g. `els_transform`, parsing `payload` into
  typed columns) doesn't exist yet.

## Status

Built 2026-10-05. `consume_telemetry_events.py`, `Dockerfile`, and `docker-compose.yml` are all
implemented; `docker compose config` was used to validate both this component's and `kafka`'s
compose-file syntax (the sandbox this was built in can't pull Docker images or reach a live
broker/SQL Server, the same constraint already documented for `kafka` itself). Verified directly:
the connection-string builder (host/port vs. named-instance branching, encrypt/trust-cert flag
mapping), the log-line formatter (including its fallback for unparseable input), the message
loop's insert-then-commit-then-offset-commit sequence, the write-failure path (confirms the
failing message's offset is never committed while an earlier, successful message's is), and a
full `main()` run end-to-end with both Kafka and the database faked out. Not yet verified: an
actual live run against the real `kafka` component and a real SQL Server — including whether
`els_accountadmin` actually has sufficient server permissions to create the `telemetry_consumer`
login, and whether the Microsoft ODBC driver install inside the Docker image actually works
end-to-end (researched against Microsoft's current documentation, not copied from training
knowledge, but not run). No CI yet.
