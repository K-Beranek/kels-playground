# telemetry-event-generator

Emulates a client application sending telemetry events as a student works through the
eLearning system, for one campus. It reads real, pre-existing data out of
[`els-database`](../els-database/) (which person, which courses, which content/tests/
submissions exist) and turns that into a stream of session/login/activity/logout events —
without ever writing anything back. By default, each event is published one at a time to the
[`kafka`](../kafka/) component's `telemetry-events` topic, keyed by `session_id`. Passing
`--sink file` (or `--sink both`) also writes — or writes instead — the same events as NDJSON to
a local, append-only file; that was this script's only output before the `kafka` component
existed, and is kept as an option for offline runs, debugging, or a side-by-side copy of what
was sent. A later component is expected to consume from that topic and write into a new
`els-database` table, the third and last part of this pipeline.

## Setup

This needs a real, read-only connection to the same SQL Server database `els-database`
deploys to, and (for the default `--sink kafka`/`both`) a reachable `kafka` component. Install
both Python dependencies:

```bash
pip install -r requirements.txt
```

That installs `pyodbc` and `kafka-python`. They have very different installation stories:

- **`pyodbc`** is a thin wrapper around a system-level ODBC driver, not a self-contained SQL
  Server client — the driver itself is a separate, OS-level install:
  - **Windows:** install "ODBC Driver 18 for SQL Server" (or 17) from Microsoft. `pyodbc` will
    find it automatically once installed.
  - **Linux (Debian/Ubuntu):** install `unixodbc` plus Microsoft's `msodbcsql18` package from
    Microsoft's `packages.microsoft.com` apt repository.
  - **macOS:** `brew tap microsoft/mssql-release && brew install msodbcsql18`.

  If the driver name installed on your machine doesn't match the default
  (`ODBC Driver 18 for SQL Server`), pass `--odbc-driver "ODBC Driver 17 for SQL Server"` (or
  whatever `odbcinst -q -d` reports as installed).

- **`kafka-python`** is pure Python — no system-level driver, no compiler, nothing beyond
  `pip install` needed, on any OS. **Make sure you get the right package**: the name on PyPI is
  `kafka-python`; a different, unrelated package is literally named `kafka` and installing that
  one instead will not work. `requirements.txt` already pins the correct one.

Connection details come from this component's **own** `config/config.json` — copy
`config/config.template.json` to `config/config.json` and fill in real values. This is a
separate file from `els-database/config/config.json`, even though both will typically point
at the same physical server — see `CLAUDE.md` for why. The template's `kafka` section
(`bootstrapServers`/`topic`) matches the `kafka` component's defaults out of the box; only
`sqlServer`/`auth` need real values if you're running everything locally.

If you only ever run this with `--sink file`, nothing Kafka-related in config or on your
machine is actually used at runtime — but `kafka-python` still needs to be installed, since the
import happens unconditionally; see `CLAUDE.md` for why that wasn't made optional.

## Running tests

The test suite needs neither a live SQL Server nor a live Kafka broker — it runs against a fake
in-memory database cursor and a fake in-memory Kafka producer, so it works offline, anywhere:

```bash
pip install -r requirements-dev.txt
pytest
```

`requirements-dev.txt` adds `pytest` on top of this component's normal runtime dependencies
(`-r requirements.txt`) — a separate file so a normal run of the script itself never needs a
test framework installed. `pytest.ini` points discovery at `tests/`; `tests/conftest.py` makes
`generate_telemetry_events.py` importable and stubs `pyodbc` if the real package can't be
imported (most dev machines and CI runners won't have a Microsoft ODBC driver installed — see
"Setup" above).

What this suite does **not** cover, because nothing short of a real SQL Server and a real Kafka
broker can: whether a real database connection or a real message delivery actually succeeds.
See `CLAUDE.md`'s "Known gaps" for exactly what has and hasn't been verified live, by hand,
against this project's `els-database`/`kafka` components.

## Usage

```bash
python generate_telemetry_events.py --campus-uuid 3fa2c1e0-... --session-count 20 --session-length 50
```

That publishes to Kafka (the default). To also keep a local NDJSON copy of the same run:

```bash
python generate_telemetry_events.py --campus-uuid 3fa2c1e0-... --session-count 20 --session-length 50 --sink both
```

| Parameter | Type | Constraint |
|---|---|---|
| `--campus-uuid` | string (uuid) | Must be a syntactically valid UUID; must match an existing `els.campus.uuid`. |
| `--session-count` | integer | 1–100. Number of sessions to simulate. |
| `--session-length` | integer | 5–100. Upper bound on the number of body events per session — the actual count per session is random, 5..`session-length`. |

Optional flags: `--sink` (default: `kafka`; `kafka`/`file`/`both`), `--output` (default:
`output/telemetry_events.ndjson`, next to this script; used when `--sink` is `file` or `both`),
`--config-path` (default: `config/config.json`), `--odbc-driver`
(default: `ODBC Driver 18 for SQL Server`), `--lookback-days` (default: `30` — see
"Session timing" below; `0` disables it).

## What one session looks like

```
SESSION_INIT                                                    -- session starts
LOGIN                                                           -- the chosen person logs in
<a random number of CONTENT_ACCESS / COURSE_TEST / SUBMISSION events, 5..session-length>
LOGOUT                                                          -- the chosen person logs out
```

The person for a session is picked by taking one random row from `els.course_person` for the
given campus and reading its `person_id` off — this naturally favours people with more course
enrolments, which mirrors reality closely enough for this exercise. Every body event in the
session can land on a *different* course the person is enrolled in — a session isn't locked to
one course, since a real student's session plausibly touches more than one.

## Event shape

Every event shares a common envelope — **except `SESSION_INIT`, which has no `person_id`**:
`SESSION_INIT` fires before `LOGIN`, so at that point the (simulated) client genuinely doesn't
know who's logging in yet.

```json
{"event_id": "...", "event_type": "SESSION_INIT", "session_id": "...", "timestamp": "2026-10-02T14:23:01.123456+00:00", "campus_id": 1}
```

Every event from `LOGIN` onward adds `person_id`:

```json
{"event_id": "...", "event_type": "LOGIN", "session_id": "...", "timestamp": "2026-10-02T14:23:02.654321+00:00", "campus_id": 1, "person_id": 42}
```

`CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION` events add their own fields on top:

```json
{"event_id": "...", "event_type": "CONTENT_ACCESS", "session_id": "...", "timestamp": "...", "campus_id": 1, "person_id": 42, "course_id": 7, "course_content_id": 103}
{"event_id": "...", "event_type": "COURSE_TEST", "session_id": "...", "timestamp": "...", "campus_id": 1, "person_id": 42, "course_id": 7, "course_test_id": 12}
{"event_id": "...", "event_type": "SUBMISSION", "session_id": "...", "timestamp": "...", "campus_id": 1, "person_id": 42, "course_id": 7, "course_test_id": 12, "submission_id": 55}
```

**Every id here is `els-database`'s own internal surrogate id** (`campus.id`, `person.id`,
`course.id`, ...) — not `campus.uuid`/`person.uuid`. See `CLAUDE.md` for why that's deliberate
rather than an oversight.

## Publishing to Kafka

When `--sink` is `kafka` or `both`, each event is sent to the configured topic (default
`telemetry-events`) individually, **keyed by `session_id`** — Kafka keeps all messages sharing a
key on the same partition, in order, so one simulated session's events are never read back out
of order relative to each other, even though different sessions may land on different
partitions. The key is the raw UTF-8 bytes of the session's UUID string; the value is the same
compact JSON encoding used for the NDJSON file, also UTF-8 bytes — `--sink both` sends the exact
same bytes to both destinations, not two independently-serialized copies.

Delivery is confirmed synchronously, one event at a time (`producer.send(...).get(timeout=10)`)
before moving on to the next — the same "one round trip per operation, fine at this scale"
choice already made for the database picks above, not a batching/throughput optimization. If a
single event's delivery fails or times out, the whole run stops immediately with a clear error
(no retry, no partial success silently treated as success) — this script never creates the topic
itself; that's the `kafka` component's `topic-init` service's job, and this script will tell you
clearly, before simulating anything, if the topic can't be found.

## Behavior worth knowing about

- **Read-only, pre-existing data only.** This tool never inserts, updates, or deletes a row —
  every `CONTENT_ACCESS`/`COURSE_TEST`/`SUBMISSION` event references a real row that was
  already sitting in `els-database` (typically put there by
  `els-database/scripts/generate-synthetic-data/`). It never fabricates a submission or a
  content item.
- **Sparse data → skip, no retry.** If the person chosen for a session has nothing matching a
  given event type (e.g. they hold the Instructor role, so they have no submissions of their
  own), that single event is silently skipped and generation moves on to the next one. A
  session can end up as just `SESSION_INIT`/`LOGIN`/`LOGOUT` if nothing else matched at all.
  The script reports how many body events were skipped at the end of the run.
- **Session timing.** Each session's start time is "now" minus a random offset of up to
  `--lookback-days` days (default 30), so `--session-count` sessions don't all cluster within
  the same few minutes of wall-clock time. Within a session, each event's timestamp advances
  from the previous one by a random 1–20 second gap (fixed constants in the script, not CLI
  flags — see `CLAUDE.md`).
- **Output is NDJSON, not a JSON document.** One compact JSON object per line, appended to the
  output file. The file as a whole is deliberately **not** valid JSON — there's no enclosing
  `[...]` array and no commas between lines — because each line is meant to become one future
  Kafka message, and NDJSON both supports real appending and maps directly onto "one line, one
  record."

## Known limitations

- One round-trip query per random pick (one per event, roughly) rather than batching —
  perfectly fine at the scale this is meant to run at (≤100 sessions × ≤100 events), but
  wouldn't scale well to a much larger run without caching the eligible content/test/
  submission pools in memory per course. The same "fine at this scale, wouldn't batch well
  beyond it" trade-off now also applies to the one-event-at-a-time Kafka delivery confirmation.
- No person-role filtering (e.g. restricting to Student-role `course_person` rows) — relying
  entirely on the "no matching data → skip" behavior instead, which was a deliberate choice,
  not an oversight (see `CLAUDE.md`).
- Single-threaded, synchronous throughout — one session at a time, one event at a time, one
  Kafka delivery confirmation at a time.
- No live SQL Server or live Kafka broker was reachable from the sandbox this was last built
  in — see `CLAUDE.md`'s "Known gaps" for exactly what has and hasn't been verified for real.
