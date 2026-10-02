# telemetry-event-generator

Emulates a client application sending telemetry events as a student works through the
eLearning system, for one campus. It reads real, pre-existing data out of
[`els-database`](../els-database/) (which person, which courses, which content/tests/
submissions exist) and turns that into a stream of session/login/activity/logout events —
without ever writing anything back. Today it writes those events to a local NDJSON file; that
file is an explicit stand-in for a future Kafka topic. A later component is expected to take
over the "where do these events go" part without this one's event-generation logic changing
at all.

## Setup

This needs a real, read-only connection to the same SQL Server database `els-database`
deploys to. Two separate things need to be installed:

```bash
pip install -r requirements.txt
```

That installs the `pyodbc` Python package — but `pyodbc` is a thin wrapper around a
system-level ODBC driver, not a self-contained SQL Server client. The driver itself is a
separate, OS-level install:

- **Windows:** install "ODBC Driver 18 for SQL Server" (or 17) from Microsoft. `pyodbc` will
  find it automatically once installed.
- **Linux (Debian/Ubuntu):** install `unixodbc` plus Microsoft's `msodbcsql18` package from
  Microsoft's `packages.microsoft.com` apt repository.
- **macOS:** `brew tap microsoft/mssql-release && brew install msodbcsql18`.

If the driver name installed on your machine doesn't match the default
(`ODBC Driver 18 for SQL Server`), pass `--odbc-driver "ODBC Driver 17 for SQL Server"` (or
whatever `odbcinst -q -d` reports as installed).

Connection details come from this component's **own** `config/config.json` — copy
`config/config.template.json` to `config/config.json` and fill in real values. This is a
separate file from `els-database/config/config.json`, even though both will typically point
at the same physical server — see `CLAUDE.md` for why.

## Usage

```bash
python generate_telemetry_events.py --campus-uuid 3fa2c1e0-... --session-count 20 --session-length 50
```

| Parameter | Type | Constraint |
|---|---|---|
| `--campus-uuid` | string (uuid) | Must be a syntactically valid UUID; must match an existing `els.campus.uuid`. |
| `--session-count` | integer | 1–100. Number of sessions to simulate. |
| `--session-length` | integer | 5–100. Upper bound on the number of body events per session — the actual count per session is random, 5..`session-length`. |

Optional flags: `--output` (default: `output/telemetry_events.ndjson`, next to this script),
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
  submission pools in memory per course.
- No person-role filtering (e.g. restricting to Student-role `course_person` rows) — relying
  entirely on the "no matching data → skip" behavior instead, which was a deliberate choice,
  not an oversight (see `CLAUDE.md`).
- Single-threaded, synchronous, and does not talk to Kafka yet — see "What's next" above.
