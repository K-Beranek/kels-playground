# telemetry-event-generator — notes for future sessions

A Python script (`generate_telemetry_events.py`) that emulates a client application sending
telemetry as a student works through the eLearning system. Read-only against
[`els-database`](../els-database/); publishes to the [`kafka`](../kafka/) component by default,
with an NDJSON file as an explicit, still-supported alternative/addition (`--sink`). See
`README.md` for usage; this file captures the decisions behind the design, most of them made
explicitly rather than defaulted to, during the planning conversations that preceded and then
extended this script.

## Identifiers: internal surrogate ids, not uuids — deliberate

`els.campus` and `els.person` each have a dedicated external `uuid` column (their comments in
`els_full_schema.sql` literally say "stable external identifier ... for APIs/integrations");
`course`, `course_content`, `course_test`, `course_person`, and `submission` do not — they only
have an internal surrogate `id`, unique per campus. The natural question was whether events
should carry `person.uuid` (the column that exists for exactly this kind of use) or the
internal `person.id`.

Resolved explicitly: **internal ids, everywhere, including `person_id`.** The reasoning given
was that this tool is emulating the *client application itself* — the thing that would already
be working entirely in terms of the database's own internal ids, not a system that looks up an
external uuid before sending every event. A real client sending telemetry about "this session,
this person, this course" already has those internal ids on hand; reaching for `uuid` here
would have been modeling a different kind of system (an external integration) than the one
actually being emulated.

## `SESSION_INIT` has no `person_id` — fixed after an initial oversight

The first draft put `person_id` in every event's envelope unconditionally, including
`SESSION_INIT`. That's wrong: `SESSION_INIT` fires *before* `LOGIN` in the event sequence this
tool simulates, so at that point the (simulated) client doesn't actually know who's logging in
yet — reporting a `person_id` on it would be inventing information the real system wouldn't
have. `make_event()` now takes `person_id` as an optional keyword (default `None`) and only
adds the key to the event dict when it's given; every call site except `SESSION_INIT`'s still
passes it. `person_id` itself is still resolved early in `generate_session()` (before
`SESSION_INIT` is even written) because the rest of the function needs it to know which
courses/content/tests/submissions to sample from — that's a generator-internal bookkeeping
detail, not something the emitted `SESSION_INIT` event claims to know.

## `campus_id` is part of the event envelope

Every id below `campus` in `els-database`'s schema is keyed `(campus_id, id)`, not just `id` —
`course_content_id: 103` on its own is ambiguous; it only means something once you know which
campus. `campus_id` is therefore in *every* event's envelope, not just implied by "this whole
run is for one campus" — a downstream consumer (the eventual Kafka→SQL Server sink) needs it
to resolve any other id in the payload.

## Course scope is per event, not per session

A session is anchored to one person (picked via one random `course_person` row for the given
campus), but **not** to that row's course. Each `CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION`
event independently picks from *any* course the person is enrolled in (any role) at that
campus — confirmed explicitly: "They can interact with several different courses during that
session." `get_eligible_course_ids()` computes that course pool once per session (it doesn't
change mid-session), and each body event samples against the whole pool, not against a
single fixed course.

## Sparse data → skip, no retry

If the randomly chosen event type has nothing to sample for this person (most commonly: they
hold the Instructor role, so `pick_submission()` finds no submission made via any of their
`course_person` rows), that event is dropped and generation moves straight to the next
iteration. Confirmed explicitly, twice: "do not retry" and "if there are no data for the
person then there would be just SESSION_INIT, LOGIN and LOGOUT events." This is also why there
is **no person-role filtering** anywhere in the script — restricting the initial
`course_person` draw to Student-role rows was considered and explicitly rejected in favour of
just letting a non-Student person's sessions come out event-light. Simpler, and it's exercising
the same "handle missing data" code path either way.

## Pre-existing data only — this tool never writes

Every `CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION` event references a row that already exists
in `els-database` (via `els-database/scripts/generate-synthetic-data/`, typically) — it is
never fabricated here. Confirmed explicitly: "This generator uses pre-existing data only. It
does not create any new records." This is also why `pick_submission()` joins through
`course_person` rather than inventing a plausible-looking submission id: a `SUBMISSION` event
without a real underlying row would misrepresent what this tool is supposed to be doing
(replaying realistic *access patterns* over real data, not generating new activity).

## Output: NDJSON, append-only, not a JSON document

One compact JSON object per line, written with Python's default file-append mode. The file as
a whole is **not** valid JSON (no enclosing array, no inter-line commas) — this was confirmed
explicitly as the intended shape, not a shortcut: each line already looks like what a future
Kafka message's value will look like, and a JSON array can't be appended to without rewriting
its closing bracket, while NDJSON can.

## Separate `config/config.json`, not a shared one with `els-database`

`els-database/docs/els-database.md`'s own "how other components should use this" guidance says
tooling needing a live connection should "go through `config/` for connection details rather
than inventing its own config mechanism" — but that line is about tooling living *inside*
`els-database/scripts/`, not about other top-level components. This repo's actual convention
(see the project's `conventions-and-roadmap.md`, and `els_transform`'s own separately-configured
`profiles.yml`) is that each top-level component owns its deployment/connection configuration
independently, even when two components happen to point at the same physical server today.
Confirmed explicitly for this component too. Worth remembering if this ever reads like a
contradiction: it isn't one, it's two different scopes of "don't invent your own config" — one
*within* a component's own tooling, one *across* components.

## Session timing: lookback window + randomized gaps

Two things were proposed together and both accepted:

- **`--lookback-days` (default 30, `0` disables it):** without it, `--session-count` sessions
  generated back-to-back in one run would all start within the same few minutes of wall-clock
  "now," which doesn't look like real usage data. Each session's start time is `now` minus a
  uniformly random offset of up to `--lookback-days` days.
- **Randomized 1–20 second gaps between events within a session**, rather than a fixed
  "+1 second per event" — a uniform one-event-per-second cadence doesn't read as a real user
  session either. `EVENT_GAP_MIN_SECONDS`/`EVENT_GAP_MAX_SECONDS` are fixed constants in the
  script, not CLI flags — the three parameters meant to be tuned from the command line are
  `campus_uuid`, `session_count`, and `session_length`; widening the CLI surface beyond what
  was actually asked for wasn't done without a reason to.

Timestamps use Python's `datetime`, timezone-aware UTC, formatted via `.isoformat()` —
microsecond precision, not true nanosecond (which would need `time.time_ns()` tracked
separately, more machinery than this needs just to get events that sort correctly and look
distinct).

## Random-row selection: SQL Server's `TOP (1) ... ORDER BY NEWID()` idiom

Every "pick one random matching row" operation (the session's person, and each
content/test/submission pick) is done **inside** the SQL query via `ORDER BY NEWID()`, not by
fetching a candidate list into Python and sampling there. This keeps randomness in one place
(the database) for the "pick a row" operations, and reuses the standard SQL Server idiom for
it — matching the `NEWID()`-per-row behaviour already discussed and understood for this
project (see the conversation history: a CTE-materialization question that came up earlier
about this same function). Python's own `random.Random` is still used for everything that
isn't "pick a database row": which body event type to attempt, the actual body-event count
(`5..session-length`), and the session-start/event-gap timing. No `--seed` option exists —
`NEWID()`-based picks can't be seeded anyway, so a seed would only make half the randomness in
a run reproducible, which was judged not worth the added CLI surface for what this tool is for.

## Publishing to Kafka: `--sink`, default `kafka`, with `file`/`both` kept as options

Added 2026-10-02, once the `kafka` component existed and was confirmed working. The NDJSON
output format had been chosen specifically so that adding a Kafka producer later wouldn't
require touching anything above `write_event()` — confirmed true in practice: `generate_session()`
is completely unchanged by this; only `write_event()`'s construction and `main()`'s setup changed.

**Default is `kafka`, not `file`, and not `both` — confirmed explicitly rather than assumed.**
The three-part pipeline this script was always the first piece of is "generator → Kafka →
SQL Server sink"; once Kafka exists, defaulting to still writing a local file only would mean
every invocation needs an extra flag to do the thing the pipeline is actually for. `file` is kept
as a real, equally-supported mode (not deprecated) for offline runs, debugging a batch of events
without a broker running, or wanting a durable local copy — and `both` for getting a local copy
of exactly what was sent, same run, same serialized bytes for each destination (see
`build_write_event()`: the JSON payload is serialized once and reused, never built twice).

**Kafka connectivity/topic-existence is checked once, upfront, before even connecting to the
database** — not discovered partway through generating sessions. `get_kafka_config()` validates
the config shape first (clear `ValueError` if the `kafka` section or its keys are missing);
then the producer's `partitions_for(topic)` is called once as the connectivity+topic-existence
probe, since `KafkaProducer(...)` itself never actually contacts the broker (see the next section
for why that matters). This also means a `--sink file` run's config doesn't need a `kafka`
section at all — backward compatible with any config.json written before this change.

**Message key is `session_id`, value is the event's JSON, both as explicit raw UTF-8 bytes** —
no `key_serializer`/`value_serializer` configured on the producer; this script encodes both
itself, the same way it already explicitly UTF-8-encodes the NDJSON file. Keying by `session_id`
was confirmed during the `kafka` component's own design (see `kafka/CLAUDE.md`) specifically so
all of one session's events land on the same partition and are never read back out of order
relative to each other, even though different sessions may spread across the topic's partitions.

**Delivery is synchronous, one event at a time** (`producer.send(...).get(timeout=10)`), not
batched-then-flushed. Deliberately mirrors the already-established "one round trip per operation,
fine at this scale" choice for the database picks (≤100 sessions × ≤100 events is nowhere near
where batching would start to matter), and keeps "did this event actually make it?" answerable
per-event rather than only at the very end of a run. A delivery failure or timeout propagates as
`kafka.errors.KafkaError`, caught in `main()` alongside `pyodbc.Error`, and stops the whole run
immediately with a clear message — no retry, no silently-continued run with a gap in it.

## Kafka client library: `kafka-python`, chosen over `confluent-kafka` — checked current state first

This was a genuine fork worth surfacing rather than deciding silently, so it was asked about
explicitly. Both libraries were confirmed actively maintained as of the research done when this
was built (2026-10): `kafka-python` had just put out v3.0.11 (Aug 2026, "Production/Stable",
171 commits in the preceding 90 days — a real revival; it had a period of much slower
maintenance in the past, which is why it was worth checking current state rather than assuming);
`confluent-kafka` is the library most real production deployments actually use, backed by
`librdkafka` (the C library most non-JVM Kafka clients wrap). The deciding factor was installation
friction, not raw capability: `kafka-python` ships as a universal pure-Python wheel, installs with
plain `pip install` on any OS with zero native dependencies, while `confluent-kafka` needs a
native wheel (Windows wheels exist but are more of an install-time edge case) — this project
already has one OS-level-dependency headache in `pyodbc`'s ODBC driver requirement, and avoiding
a second one for a comparatively low-stakes learning component was worth the (real, acknowledged)
trade-off of not using the client most production Kafka deployments reach for.

## `kafka-python`'s `KafkaProducer` does **not** fail fast by default — tested directly, not assumed

This is the single most important thing to know before touching this script's Kafka setup code,
and it was discovered by testing, not by reading documentation: against a deliberately
unreachable address, `KafkaProducer(bootstrap_servers=...)` constructs instantly (it never
actually contacts the broker at construction time — it only prepares local client state), and
then `producer.send(...)`, `future.get(timeout=...)`, and even `producer.partitions_for(...)`
**all hung past 20-30 seconds** with no exception, regardless of `request_timeout_ms`. The cause,
confirmed by inspecting `KafkaProducer`'s accepted config keys directly: this version has **no
exposed way to bound the broker-API-version auto-detection probe** that happens before any of
those calls can proceed — older `kafka-python` versions had an `api_version_auto_timeout_ms`
setting for exactly this; this version's accepted-config list doesn't include it at all.

**The fix, verified by testing against the same unreachable address: pass `api_version` and
`max_block_ms` explicitly.** Setting `api_version` skips the auto-detection probe entirely (the
client is simply told what protocol version to assume, instead of asking); `max_block_ms` then
bounds how long `send()`/`partitions_for()` may block waiting for metadata before raising
`KafkaTimeoutError` (a `KafkaError` subclass). With both set, the exact same unreachable-address
test failed in exactly the configured time, with a clear exception, every time. `KAFKA_API_VERSION`
is hardcoded to `(4, 1, 2)` — matching the `kafka` component's own pinned `apache/kafka:4.1.2` —
on the reasoning that this script only ever talks to that specific component's broker; if the
`kafka` component's pinned version ever changes, this constant needs to change with it.
`KAFKA_MAX_BLOCK_MS`/`KAFKA_REQUEST_TIMEOUT_MS` both reuse `KAFKA_DELIVERY_TIMEOUT_SECONDS` (10s)
rather than being separately-tuned magic numbers.

Worth remembering generally, not just for this script: a client library's defaults are not
guaranteed to fail fast just because that would obviously be the more helpful behavior — this is
exactly the kind of thing to actually test against a real unreachable endpoint before trusting,
the same discipline already applied to the Kafka Docker permission errors in `kafka/CLAUDE.md`.

## `kafka-python` is a hard, unconditional import — even for `--sink file`

Mirrors the existing `pyodbc` import pattern exactly (`try: import ... except ImportError: sys.exit(...)`
with an actionable message) rather than making it conditional on `--sink`. This is a deliberate
simplification: the default `--sink` is `kafka`, so the overwhelming majority of runs need the
import anyway, and `kafka-python`'s install cost is genuinely low (pure Python, no native
dependency, unlike `pyodbc`'s ODBC driver) — not worth the added branching of making one import
conditional on a CLI flag that hasn't even been parsed yet at import time. A `--sink file`-only
user still needs `kafka-python` installed, but never needs it to actually work (no connection is
attempted when `--sink` doesn't include `kafka`).

## Known gaps, flagged rather than filled in speculatively

- No CI wired up yet.
- Not yet run against a live SQL Server or a live Kafka broker from any sandbox this script has
  been built in — neither was reachable. What *has* been verified for real, directly, not just
  reasoned about: the event-generation logic (dry-run test suite against a fake in-memory
  cursor — normal sessions, the sparse-data skip path, the eligible-course/picker functions);
  `build_write_event()`'s three sink modes including key/value encoding (fake producer, asserting
  on exactly what bytes/key would be sent); a full `main()` run end-to-end with both the database
  connection and the Kafka producer faked out, checking the real CLI/config-loading/error-handling
  path, not just the inner generation functions; and, run as an actual subprocess rather than a
  unit test, all three Kafka-related CLI error paths (unreachable broker times out cleanly in the
  configured window with a clear message; `--sink file` skips Kafka setup entirely when the
  config has no `kafka` section; `--sink both` fails clearly, before touching the database, when
  the `kafka` section is missing). What's still unverified: an actual successful delivery to a
  real broker, and the real `pyodbc` connection path — both pending a run on a machine with both
  reachable.
- The Kafka→SQL Server consumer (the third and last part of the original plan) doesn't exist
  yet.
