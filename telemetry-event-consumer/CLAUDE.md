# telemetry-event-consumer — notes for future sessions

A Python script (`consume_telemetry_events.py`) that consumes the `kafka` component's
`telemetry-events` topic and writes each message, unparsed, into `els-database`'s
`events.telemetry_event` landing table. Third and last part of the generator → Kafka → SQL Server
pipeline started 2026-10-02 / 2026-10-05. See `README.md` for usage; this file captures the design
decisions and why they were made, several of them answers to genuine forks Karel chose between
rather than defaults picked silently.

## Why this is a pure sink, not a transform

The table's own shape (`payload NVARCHAR(MAX)`, `row_inserted_time DATETIME2`) was already decided
before this consumer was designed, and it drove the consumer's shape in turn: `payload` stores the
exact JSON bytes Kafka delivered, byte-for-byte, and `row_inserted_time` is stamped at insert time
(`SYSUTCDATETIME()`, server-side) rather than read from the event itself. This is a standard "raw
landing zone" pattern — store the source data unmodified, parse/type it later, downstream, where a
mistake in the parsing logic doesn't require re-ingesting from Kafka to fix. The event's own
timestamp isn't lost by this choice; it's simply inside `payload` already, not duplicated into its
own column.

One real, deliberate exception: `describe_for_log()` does parse the payload as JSON, but *only* to
produce a human-readable console log line (`event_type session=session_id`) — the parsed result is
never what gets stored. If parsing fails (shouldn't happen given what the generator produces, but
this is a log line, not the insert path), it falls back to a truncated raw preview rather than
raising, so a logging nicety can never crash message processing.

## Consumer library and language: Python + kafka-python, not confluent-kafka or C#

Three options were raised explicitly, not defaulted: Python + `kafka-python` (same library as the
producer), Python + `confluent-kafka` (a deliberate fork from the producer's library, to compare
it against `kafka-python`'s known rough edges), and C# + `Confluent.Kafka` (new-language practice,
a natural "redundant implementation" twin of the Python generator, per this repo's own convention
of building the same pipeline stage more than once). Karel chose `kafka-python`, for consistency
with the producer and lowest friction — the comparison exercise and the C# twin both remain
genuinely open future work, not rejected, just not done now.

A fourth option — Kafka Connect with a JDBC sink connector, no custom code at all — was raised too,
since that's genuinely how most production shops solve "land Kafka messages into a relational
table." Not chosen, since the point of this repo is hands-on practice with a consumer API, not
with Connect's connector configuration. Worth remembering as the more realistic production answer
if this project ever wants to practice Kafka Connect specifically.

## `api_version`/`request_timeout_ms` set explicitly, carried over from the producer — not
## independently re-verified here

`telemetry-event-generator` found, by direct testing, that `kafka-python` 3.0.11's `KafkaProducer`
does not fail fast against an unreachable broker unless `api_version` and `max_block_ms` are both
set explicitly (see that component's `CLAUDE.md` for the full diagnosis). `KafkaConsumer` shares
the same underlying client/broker-connection code that caused it, so `api_version=(4, 1, 2)` and
`request_timeout_ms=10_000` are set here defensively, by analogy. **This has not been independently
re-tested against a live broker from this consumer** — flagged explicitly rather than claimed as
verified, consistent with this repo's "verify, don't assume" habit: the honest status is "a known
fix applied for a good, specific reason," not "a bug found and fixed here too."

## Orchestration: a continuous process in Docker, not a scheduled batch job

Two shapes were raised: a long-running consumer that stays connected and writes rows as messages
arrive (the idiomatic way to consume from Kafka), versus a scheduled batch job that starts, drains
whatever's available, writes it, and exits (closer to a traditional ETL job, and a plausible
dedicated-Jenkins-practice exercise — see `conventions-and-roadmap.md`). Karel chose the continuous
model. Consequences that follow directly from that choice:

- `for message in consumer:` blocks indefinitely waiting for new messages — there is no "caught
  up, exit now" condition, by design. The process is meant to run forever.
- It needs a process supervisor, not a scheduler: `docker-compose.yml`'s `restart: unless-stopped`
  fills that role. See "Delivery semantics" below for how this interacts with crash recovery.
- `kafka`'s own `docker-compose.yml` is explicit that "no application code lives here" (see that
  component's `CLAUDE.md`) — so this had to be its own component with its own `docker-compose.yml`,
  joining `kafka`'s network from outside (`external: true`) rather than being added as a new
  service in `kafka`'s own compose file.
- `kafka`'s default Docker network previously had no explicit name (Compose derives one from the
  project/folder name, `kafka` → `kafka_default`) — given a stable explicit name
  (`els-kafka-net`) specifically so this component's separate compose file has something reliable
  to join, independent of folder naming or which directory `docker compose` is invoked from. See
  `kafka/CLAUDE.md` for that change.

## Delivery semantics: at-least-once, duplicates accepted rather than engineered around

Kafka only guarantees at-least-once delivery without real transactional processing (considered
overkill here). The concrete failure window: this container crashes *after* a database `INSERT`
commits but *before* that message's Kafka offset is committed — on restart (via `restart:
unless-stopped`), the message is redelivered and reinserted.

Two designs were raised: add `kafka_partition`/`kafka_offset` columns with a unique constraint,
making the insert naturally idempotent against redelivery, versus leaving the table as-is and
documenting duplicate-on-crash as a known, accepted gap. **Karel chose to leave the table as-is.**
This is a real, open gap, not a trade-off quietly resolved — a duplicate row from this failure mode
cannot currently be detected or cleaned up after the fact, since nothing ties a row back to the
Kafka message that produced it. Revisit if this ever matters (e.g. before any real analysis is
built on top of `events.telemetry_event`).

Offsets are committed manually (`enable_auto_commit=False`), only after the corresponding row is
written (`consumer.commit()` immediately after `connection.commit()`), specifically to keep the gap
on the "possible duplicate" side rather than the "silently lost event" side — Kafka's auto-commit
default would mark a message done before this consumer knows whether the database write actually
succeeded.

On a database write failure, the process **stops immediately and does not continue** — no retry,
no silent skip of the failing message — the same convention already used by
`generate_telemetry_events.py` and `generate_synthetic_data.py`. This is a deliberate synergy with
the continuous-Docker-process choice above: under `restart: unless-stopped`, failing loud and
exiting just means the container restarts and resumes from the last *committed* offset
automatically, with no separate retry logic needed in the script itself.

## Least-privilege SQL login: `telemetry_consumer`, INSERT-only on one table

Every other component so far connects as `els_accountadmin` (effectively an admin account, used
for schema migrations and read-heavy work). This consumer is the first thing in the repo built to
connect as a dedicated, narrowly-scoped login — `telemetry_consumer`, granted `INSERT` on
`events.telemetry_event` and nothing else (`els-database/migrations/events/V0002__...sql` and
`R__01_grant_telemetry_consumer.sql`). The grant was deliberately scoped to the one table, not
`GRANT INSERT ON SCHEMA::events`, on the reasoning that this consumer has no business touching any
future additional landing table that might show up in that schema later — widen it with its own
migration if that ever actually happens, rather than granting ahead of need.

Creating that login introduced a genuinely new technique for this repo: **Flyway placeholders**
(`${telemetry_consumer_password}` in the migration SQL, supplied via a new `-Placeholders`
parameter on `Invoke-ElsMigration.ps1`, never written to any file). Every other secret in this repo
follows the "commit a template, gitignore the real file" pattern, which doesn't fit a migration
file — migrations are meant to be identical, version-controlled SQL for every environment, not
something with a gitignored real copy. Placeholders solve the same problem (never commit a secret)
a different way, appropriate to what a migration actually is. See
`els-database/migrations/events/V0002__telemetry_consumer_login.sql` for the full reasoning,
including the real risk flagged there: `CREATE LOGIN` is server-scoped and needs real server
permissions, which `els_accountadmin` may or may not have.

## Known gaps, flagged rather than filled in speculatively

- Not yet run against a live Kafka broker or live SQL Server — neither was reachable from the
  sandbox this was built in. The `api_version`/`request_timeout_ms` carry-over above and the
  `host.docker.internal`/`broker:19092` addressing are both reasoned from documented facts and the
  producer's own prior findings, not independently verified live.
- Duplicate-on-crash is a known, accepted gap (see "Delivery semantics" above), not a bug.
- No CI wired up yet, consistent with the rest of the repo at this point.
- The comparison exercise (`kafka-python` vs `confluent-kafka` for a consumer) and a C# twin of
  this component both remain genuinely open future work, not rejected — see "Consumer library and
  language" above.
