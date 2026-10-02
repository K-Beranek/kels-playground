# telemetry-event-generator — notes for future sessions

A Python script (`generate_telemetry_events.py`) that emulates a client application sending
telemetry as a student works through the eLearning system. Read-only against
[`els-database`](../els-database/); writes an NDJSON file today, a future Kafka producer
tomorrow. See `README.md` for usage; this file captures the decisions behind the design, most
of them made explicitly rather than defaulted to, during the planning conversation that
preceded this script.

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

## Known gaps, flagged rather than filled in speculatively

- No CI wired up yet.
- Not yet run against a live SQL Server from this sandbox (no SQL Server reachable here) — the
  event-generation logic itself is covered by a dry-run test suite against a fake in-memory
  cursor (exercising normal sessions, the sparse-data skip path, and the eligible-course/picker
  functions directly), but the real `pyodbc` connection path is unverified beyond code review.
- No Kafka integration yet — this is the explicitly-scoped first half of a three-part plan
  (`telemetry-event-generator` → a Kafka component → a consumer writing into a new
  `els-database` table). The NDJSON output format was chosen specifically so that swapping the
  file-append step for a Kafka producer call later shouldn't require touching anything above
  `write_event()`.
