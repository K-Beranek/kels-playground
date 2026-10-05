# Review: Telemetry Event Generator (`telemetry-event-generator`)

## What it is

A Python script that emulates a client application sending telemetry events as a student
works through the eLearning system, for one campus. It reads real, pre-existing data out of
`els-database` (a random person enrolled at the campus, the courses they belong to, their
existing content/test/submission activity) and turns it into a stream of
`SESSION_INIT`/`LOGIN`/`CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION`/`LOGOUT` events. By default
each event is published to the [`kafka`](../kafka/) component's `telemetry-events` topic, keyed
by `session_id`; `--sink file`/`both` writes (or also writes) the same events as NDJSON to a
local file, which was this script's only output before `kafka` existed. This is the first part of
a three-part pipeline, now complete in design: this generator → [`kafka`](../kafka/) →
[`telemetry-event-consumer`](../telemetry-event-consumer/), which writes events into a new
`els-database` table. See that component's review for what's actually been verified live.

## Key decisions

- **Internal surrogate ids, not external uuids, for every id in every event — including `person_id`.** `campus` and `person` both have a dedicated external `uuid` column designed for exactly this kind of use, but this tool deliberately emulates the *client application itself*, which would already be working in terms of the database's own internal ids rather than resolving an external uuid before every event. A different kind of system (an external integration) would have made the opposite call.
- **Every event's envelope includes `person_id` *except* `SESSION_INIT`.** `SESSION_INIT` fires before `LOGIN`, so at that point the client doesn't know who's logging in yet — reporting a `person_id` there would claim information the real system wouldn't have. Caught and fixed after the first draft put it on every event unconditionally.
- **`campus_id` is in every event's envelope, not just implied by the run.** Every id below `campus` in the schema is scoped `(campus_id, id)`, not globally unique on its own — a downstream consumer needs `campus_id` on hand to resolve any other id in the payload.
- **A session's course scope is per-event, not fixed for the whole session.** The person is picked once per session (via one random `course_person` row for the campus), but each body event independently samples from any course that person is enrolled in — a real session can plausibly touch more than one course.
- **Sparse data skips the event; it never retries or substitutes.** If the chosen event type has nothing to sample for this person (most commonly: an Instructor with no submissions of their own), that single event is dropped and generation moves on — a session can come out as just `SESSION_INIT`/`LOGIN`/`LOGOUT`. This is also why there's no person-role filtering anywhere: it relies on this same skip behavior instead of restricting the initial draw to Student-role rows.
- **Strictly read-only against pre-existing data.** Every `CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION` event references a row that already exists in `els-database` — nothing is fabricated or written back.
- **Output is NDJSON, not a single JSON document, and the file is append-only.** One compact JSON object per line; the file as a whole is deliberately not valid JSON (no enclosing array, no inter-line commas) — a direct match for what a future Kafka message's value will look like, and something a JSON array can't support without rewriting its closing bracket on every run.
- **Its own `config/config.json`, independent of `els-database`'s.** Each top-level component owns its connection configuration, even though both currently point at the same physical SQL Server instance — consistent with how `els_transform` configures its own `profiles.yml` rather than reaching into `els-database/config/`.
- **Session start times are spread over a configurable lookback window (default 30 days), and inter-event gaps are randomized (1–20 seconds), rather than everything clustering at "now" one second apart.** Both added as realism improvements beyond the literal spec, confirmed as wanted rather than assumed.
- **`--sink` defaults to `kafka`, not `file`.** Once `kafka` existed, defaulting to still writing a local-only file would mean every run needs an extra flag to do what the three-part pipeline is actually for; `file`/`both` are kept as fully-supported options (offline runs, debugging, a local copy of what was sent), not deprecated.
- **`kafka-python`, not `confluent-kafka`, chosen after checking both were actively maintained.** The deciding factor was installation friction, not capability: `kafka-python` is a pure-Python universal wheel (no native dependency, unlike this project's existing `pyodbc`/ODBC-driver pain); `confluent-kafka` is closer to what most real production deployments use, but needs a native wheel.
- **`kafka-python`'s `KafkaProducer` does not fail fast against an unreachable broker by default — found by testing, not assumed.** `send()`/`partitions_for()` hung past 20-30 seconds with no exception until `api_version` (skips an unbounded auto-detection probe this version has no way to time-box otherwise) and `max_block_ms` were both set explicitly. See `CLAUDE.md` for the full story — a good example of why a library's defaults shouldn't be trusted to fail fast just because that would obviously be the more helpful behavior.
- **Kafka delivery is synchronous and per-event** (`send(...).get(timeout=10)`), keyed by `session_id` so one session's events stay in order on one partition — mirrors the already-established "one round trip per operation" choice for the database picks, and any delivery failure stops the whole run immediately rather than continuing with a silent gap.

## How other components should use this

- Reads `els-database`'s deployed `els` schema directly (read-only) — a second component to build on top of `els-database`, alongside `els_transform`.
- Publishes to the [`kafka`](../kafka/) component's `telemetry-events` topic by default — the first leg of the generator → Kafka → SQL Server pipeline. [`telemetry-event-consumer`](../telemetry-event-consumer/) reads that topic and writes into a new `els-database` table, completing the pipeline in design.
- Does not read `els-data-model` or `els_transform` at all.

## Status

Built 2026-10-02, extended the same day once `kafka` existed: argument validation
(`--campus-uuid`, `--session-count` 1–100, `--session-length` 5–100, `--lookback-days`), full
session-generation logic, NDJSON output, and Kafka publishing (`--sink kafka`/`file`/`both`) are
all implemented. Verified for real, directly: the event-generation logic (dry-run test suite
against a fake in-memory database cursor), the sink-selection logic (fake Kafka producer,
asserting on exact key/value bytes), a full `main()` run end-to-end with both the database and
Kafka producer faked out, and — run as an actual subprocess, not a unit test — all three
Kafka-related CLI error paths (clean timeout against an unreachable broker, `--sink file`
correctly needing no Kafka config, `--sink both` correctly failing clearly when Kafka config is
missing). Not yet verified: an actual successful delivery to a real broker, and the real
`pyodbc` connection path — neither a live SQL Server nor a live Kafka broker was reachable from
the sandbox this was built in. The consumer-side SQL Server sink is the next planned component.

The dry-run test suite above was converted into a proper, committed `pytest` suite the same day
(`tests/`, `tests/conftest.py`, `pytest.ini`, `requirements-dev.txt`) — the first component in
this repo with a committed test suite. `pip install -r requirements-dev.txt && pytest` runs all
13 tests offline, with no live SQL Server or Kafka broker needed, since everything is exercised
against hand-written fakes. No CI wired up yet to run it automatically — that's a deliberate next
step, not an oversight; see the project's `conventions-and-roadmap.md` for what a GitHub Actions
workflow for this component would look like.
