# Review: Telemetry Event Generator (`telemetry-event-generator`)

## What it is

A Python script that emulates a client application sending telemetry events as a student
works through the eLearning system, for one campus. It reads real, pre-existing data out of
`els-database` (a random person enrolled at the campus, the courses they belong to, their
existing content/test/submission activity) and turns it into a stream of
`SESSION_INIT`/`LOGIN`/`CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION`/`LOGOUT` events, written one
JSON object per line to a local NDJSON file. It is the first of a planned three-part pipeline:
this generator → a Kafka component → a consumer that writes events into a new `els-database`
table. Only the first part exists so far; nothing here talks to Kafka yet.

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

## How other components should use this

- Reads `els-database`'s deployed `els` schema directly (read-only) — a second component to build on top of `els-database`, alongside `els_transform`.
- Its NDJSON output (`output/telemetry_events.ndjson` by default) is the intended input for the next planned component (a Kafka producer step) — nothing consumes it yet.
- Does not read `els-data-model` or `els_transform` at all.

## Status

Built 2026-10-02: argument validation (`--campus-uuid`, `--session-count` 1–100,
`--session-length` 5–100, `--lookback-days`), full session-generation logic, and NDJSON output
are implemented and covered by a dry-run test suite against a fake in-memory database cursor
(normal session shape, the sparse-data skip path, and the eligible-course/picker functions
tested directly) — no live SQL Server was reachable in this sandbox, so the real `pyodbc`
connection path is unverified beyond code review. No CI yet. No Kafka integration yet — that
and the consumer-side SQL Server sink are the next two planned components.
