#!/usr/bin/env python3
"""
generate_telemetry_events.py

Emulates a client application sending telemetry events as a student works through the
eLearning system, for one campus. This is a stand-in for a future Kafka producer: it does
not send anything over the network yet -- it writes one JSON object per line (NDJSON) to an
append-only output file. A later component is expected to replace the "append to a file"
step with "publish to a Kafka topic" without touching the event-generation logic below.

This tool is strictly read-only against the database: it never creates, updates, or deletes
any els-database row. Every event references real, pre-existing data (a real person, a real
course, a real piece of content/test/submission) -- it never fabricates a submission or a
content item that doesn't already exist. If the randomly chosen person has no matching data
for a given event type (e.g. they hold the Instructor role, not Student, so they have no
submissions of their own), that single event is skipped and generation moves straight on to
the next one -- there is no retry and no substitution.

What one simulated session looks like:
    SESSION_INIT                                   -- session starts
    LOGIN                                          -- the chosen person logs in
    <a random number of CONTENT_ACCESS/COURSE_TEST/SUBMISSION events, 5..session-length>
    LOGOUT                                         -- the chosen person logs out

Every event shares a common envelope: event_id, event_type, session_id, timestamp, campus_id.
person_id is also part of that envelope for every event type EXCEPT SESSION_INIT, which fires
before LOGIN -- at that point the (simulated) client doesn't know who's logging in yet, so
there is no person_id to report. CONTENT_ACCESS/COURSE_TEST/SUBMISSION events add their own
type-specific fields on top
(course_id plus the relevant content/test/submission id). Every id used, in the envelope and
in the payload, is els-database's own internal surrogate id -- not an external uuid. That's
deliberate: this tool emulates the real client application, which would already be working
with those internal ids rather than looking a campus-scoped uuid up for every event. See this
component's CLAUDE.md for this and several other decisions baked into the script.

Usage:
    python generate_telemetry_events.py --campus-uuid 3fa2c1e0-... --session-count 20 \\
        --session-length 50
    python generate_telemetry_events.py --campus-uuid 3fa2c1e0-... --session-count 5 \\
        --session-length 10 --output ./output/telemetry_events.ndjson \\
        --config-path ./config/config.json --odbc-driver "ODBC Driver 17 for SQL Server" \\
        --lookback-days 0
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pyodbc
except ImportError:
    sys.exit(
        "The 'pyodbc' package is required but is not installed.\n"
        "Install it with:\n"
        "    pip install -r requirements.txt\n"
        "pyodbc also needs a Microsoft ODBC Driver for SQL Server installed at the OS level --\n"
        "see README.md's Setup section, this is not something 'pip install' can provide."
    )

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR / "config" / "config.json"
DEFAULT_OUTPUT_PATH = SCRIPT_DIR / "output" / "telemetry_events.ndjson"
DEFAULT_ODBC_DRIVER = "ODBC Driver 18 for SQL Server"

# "number_of_events" per session is a random integer in this range (upper bound is
# --session-length). The lower bound of 5 is fixed, exactly as specified -- not a flag, since
# it's part of the behaviour being simulated, not a tuning knob.
MIN_BODY_EVENTS = 5

BODY_EVENT_TYPES = ("CONTENT_ACCESS", "COURSE_TEST", "SUBMISSION")

# Gap between consecutive events within a session, in seconds. Fixed constants rather than
# CLI flags -- the three parameters meant to be tuned from the command line are campus_uuid,
# session_count, and session_length; see CLAUDE.md.
EVENT_GAP_MIN_SECONDS = 1.0
EVENT_GAP_MAX_SECONDS = 20.0

# Default spread of session start times into the past, so --session-count sessions don't all
# cluster within the same few minutes of wall-clock "now". 0 disables spreading entirely.
DEFAULT_LOOKBACK_DAYS = 30


def session_count_type(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--session-count must be an integer, got {raw_value!r}")
    if not (1 <= value <= 100):
        raise argparse.ArgumentTypeError(f"--session-count must be between 1 and 100, got {value}")
    return value


def session_length_type(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--session-length must be an integer, got {raw_value!r}")
    if not (5 <= value <= 100):
        raise argparse.ArgumentTypeError(f"--session-length must be between 5 and 100, got {value}")
    return value


def lookback_days_type(raw_value: str) -> int:
    try:
        value = int(raw_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--lookback-days must be an integer, got {raw_value!r}")
    if value < 0:
        raise argparse.ArgumentTypeError(f"--lookback-days must be >= 0, got {value}")
    return value


def campus_uuid_type(raw_value: str) -> str:
    try:
        uuid.UUID(raw_value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--campus-uuid must be a valid UUID, got {raw_value!r}")
    return raw_value


def build_connection_string(config: dict, odbc_driver: str) -> str:
    """Mirrors els-database/scripts/generate-synthetic-data/generate_synthetic_data.py's
    function of the same name -- same config shape, same ODBC connection string. Deliberately
    kept as its own copy rather than shared as a common module; see this component's CLAUDE.md
    for why."""
    sql_server = config["sqlServer"]
    auth = config["auth"]

    instance_name = sql_server.get("instanceName") or ""
    if instance_name:
        server = f"{sql_server['host']}\\{instance_name}"
    else:
        server = f"{sql_server['host']},{sql_server.get('port', 1433)}"

    encrypt = "yes" if sql_server.get("encrypt", True) else "no"
    trust_cert = "yes" if sql_server.get("trustServerCertificate", False) else "no"

    return (
        f"DRIVER={{{odbc_driver}}};"
        f"SERVER={server};"
        f"DATABASE={sql_server['database']};"
        f"UID={auth['user']};"
        f"PWD={auth['password']};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
    )


def resolve_campus_id(cursor: "pyodbc.Cursor", campus_uuid: str) -> int | None:
    cursor.execute("SELECT id FROM els.campus WHERE uuid = ?;", campus_uuid)
    row = cursor.fetchone()
    return row.id if row else None


def campus_has_course_person(cursor: "pyodbc.Cursor", campus_id: int) -> bool:
    cursor.execute("SELECT TOP (1) 1 AS hit FROM els.course_person WHERE campus_id = ?;", campus_id)
    return cursor.fetchone() is not None


def pick_session_person(cursor: "pyodbc.Cursor", campus_id: int) -> int:
    """Picks one random course_person row for this campus -- SQL Server's standard "random
    row" idiom, TOP (1) ... ORDER BY NEWID(), which evaluates fresh on every call -- and
    returns its person_id. Caller must have already confirmed campus_has_course_person()."""
    cursor.execute(
        "SELECT TOP (1) person_id FROM els.course_person WHERE campus_id = ? ORDER BY NEWID();",
        campus_id,
    )
    row = cursor.fetchone()
    assert row is not None, "caller must check campus_has_course_person() first"
    return row.person_id


def get_eligible_course_ids(cursor: "pyodbc.Cursor", campus_id: int, person_id: int) -> list[int]:
    """Every course this person is associated with at this campus, in any role -- the pool
    CONTENT_ACCESS/COURSE_TEST events draw from for the rest of the session. Computed once per
    session: which courses a person belongs to doesn't change mid-session, only which course
    a given event happens to land on."""
    cursor.execute(
        "SELECT DISTINCT course_id FROM els.course_person WHERE campus_id = ? AND person_id = ?;",
        campus_id, person_id,
    )
    return [row.course_id for row in cursor.fetchall()]


def pick_content_access(cursor: "pyodbc.Cursor", campus_id: int, course_ids: list[int]) -> dict | None:
    placeholders = ",".join("?" for _ in course_ids)
    cursor.execute(
        f"SELECT TOP (1) id, course_id FROM els.course_content "
        f"WHERE campus_id = ? AND course_id IN ({placeholders}) ORDER BY NEWID();",
        campus_id, *course_ids,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {"course_id": row.course_id, "course_content_id": row.id}


def pick_course_test(cursor: "pyodbc.Cursor", campus_id: int, course_ids: list[int]) -> dict | None:
    placeholders = ",".join("?" for _ in course_ids)
    cursor.execute(
        f"SELECT TOP (1) id, course_id FROM els.course_test "
        f"WHERE campus_id = ? AND course_id IN ({placeholders}) ORDER BY NEWID();",
        campus_id, *course_ids,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {"course_id": row.course_id, "course_test_id": row.id}


def pick_submission(cursor: "pyodbc.Cursor", campus_id: int, person_id: int) -> dict | None:
    """Picks an existing submission actually made by this person. Submission references
    course_person_id, not person_id, directly -- hence the join -- which also conveniently
    hands back the course_id the submission belongs to."""
    cursor.execute(
        "SELECT TOP (1) s.id AS submission_id, s.course_test_id, cp.course_id "
        "FROM els.submission s "
        "JOIN els.course_person cp ON s.campus_id = cp.campus_id AND s.course_person_id = cp.id "
        "WHERE s.campus_id = ? AND cp.person_id = ? "
        "ORDER BY NEWID();",
        campus_id, person_id,
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "course_id": row.course_id,
        "course_test_id": row.course_test_id,
        "submission_id": row.submission_id,
    }


def pick_body_event(
    cursor: "pyodbc.Cursor",
    event_type: str,
    campus_id: int,
    course_ids: list[int],
    person_id: int,
) -> dict | None:
    if event_type == "CONTENT_ACCESS":
        return pick_content_access(cursor, campus_id, course_ids)
    if event_type == "COURSE_TEST":
        return pick_course_test(cursor, campus_id, course_ids)
    if event_type == "SUBMISSION":
        return pick_submission(cursor, campus_id, person_id)
    raise ValueError(f"unknown body event type: {event_type!r}")


def make_event(
    event_type: str,
    session_id: str,
    campus_id: int,
    event_time: datetime,
    person_id: int | None = None,
    extra: dict | None = None,
) -> dict:
    """person_id is optional and omitted by default: SESSION_INIT fires before LOGIN, so at
    that point the (simulated) client doesn't know who's logging in yet -- there is no
    person_id to report. Every other event type passes person_id explicitly."""
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "session_id": session_id,
        "timestamp": event_time.isoformat(),
        "campus_id": campus_id,
    }
    if person_id is not None:
        event["person_id"] = person_id
    if extra:
        event.update(extra)
    return event


def generate_session(
    cursor: "pyodbc.Cursor",
    campus_id: int,
    session_length: int,
    rng: random.Random,
    lookback_days: int,
    write_event,
) -> tuple[int, int]:
    """Generates and writes one full session's events. Returns (events_written, events_skipped)."""
    session_id = str(uuid.uuid4())
    person_id = pick_session_person(cursor, campus_id)
    eligible_course_ids = get_eligible_course_ids(cursor, campus_id, person_id)

    now = datetime.now(timezone.utc)
    if lookback_days > 0:
        session_start = now - timedelta(seconds=rng.uniform(0, lookback_days * 86400))
    else:
        session_start = now

    current_time = session_start
    written = 0
    skipped = 0

    def advance() -> None:
        nonlocal current_time
        current_time += timedelta(seconds=rng.uniform(EVENT_GAP_MIN_SECONDS, EVENT_GAP_MAX_SECONDS))

    # No person_id here: SESSION_INIT fires before LOGIN, so the (simulated) client doesn't
    # know who's logging in yet. person_id is drawn above only so the rest of this function
    # knows which course/content/test/submission pool to sample from -- not because the real
    # client would know it this early.
    write_event(make_event("SESSION_INIT", session_id, campus_id, current_time))
    written += 1

    advance()
    write_event(make_event("LOGIN", session_id, campus_id, current_time, person_id))
    written += 1

    number_of_events = rng.randint(MIN_BODY_EVENTS, session_length)
    for _ in range(number_of_events):
        event_type = rng.choice(BODY_EVENT_TYPES)
        extra = pick_body_event(cursor, event_type, campus_id, eligible_course_ids, person_id)
        if extra is None:
            # Sparse data: this person has nothing to sample for this event type (e.g. an
            # Instructor with no submissions of their own). Skip -- no retry, no substitution,
            # time does not advance for a skipped event.
            skipped += 1
            continue
        advance()
        write_event(make_event(event_type, session_id, campus_id, current_time, person_id, extra))
        written += 1

    advance()
    write_event(make_event("LOGOUT", session_id, campus_id, current_time, person_id))
    written += 1

    return written, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--campus-uuid", required=True, type=campus_uuid_type,
        help="els.campus.uuid of the campus to simulate sessions for.",
    )
    parser.add_argument(
        "--session-count", required=True, type=session_count_type,
        help="Number of sessions to simulate, 1-100.",
    )
    parser.add_argument(
        "--session-length", required=True, type=session_length_type,
        help="Upper bound (5-100) on the number of body events (CONTENT_ACCESS/COURSE_TEST/"
             "SUBMISSION) per session -- the actual count is random, 5..session-length.",
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT_PATH,
        help="NDJSON file to append events to -- one JSON object per line, created (along with "
             "its parent folder) if it doesn't exist yet (default: %(default)s). The file as a "
             "whole is not valid JSON -- no enclosing array, no commas between lines -- that's "
             "deliberate, see README.md.",
    )
    parser.add_argument(
        "--config-path", type=Path, default=DEFAULT_CONFIG_PATH,
        help="Path to the JSON config file with sqlServer/auth connection details "
             "(default: %(default)s).",
    )
    parser.add_argument(
        "--odbc-driver", default=DEFAULT_ODBC_DRIVER,
        help="Name of the installed Microsoft ODBC driver for SQL Server to connect with "
             "(default: %(default)s). Change this if your machine has a different version "
             "installed -- see README.md.",
    )
    parser.add_argument(
        "--lookback-days", type=lookback_days_type, default=DEFAULT_LOOKBACK_DAYS,
        help="Spread session start times uniformly over the last N days instead of clustering "
             "all --session-count sessions at 'now' (default: %(default)s). 0 disables spreading.",
    )
    args = parser.parse_args()

    if not args.config_path.exists():
        print(
            f"Error: config file not found at '{args.config_path}'. Copy "
            "config/config.template.json to config/config.json and fill in real values first.",
            file=sys.stderr,
        )
        return 1

    config = json.loads(args.config_path.read_text(encoding="utf-8"))
    connection_string = build_connection_string(config, args.odbc_driver)

    try:
        # autocommit=True: this script only ever reads (SELECT) -- there is nothing to commit
        # or roll back.
        connection = pyodbc.connect(connection_string, autocommit=True)
    except pyodbc.Error as e:
        print(f"Error: could not connect to the database: {e}", file=sys.stderr)
        return 1

    try:
        cursor = connection.cursor()

        campus_id = resolve_campus_id(cursor, args.campus_uuid)
        if campus_id is None:
            print(f"Error: no campus found with uuid '{args.campus_uuid}'.", file=sys.stderr)
            return 1

        if not campus_has_course_person(cursor, campus_id):
            print(
                f"Error: campus '{args.campus_uuid}' has no course_person records -- "
                "nothing to simulate a session for.",
                file=sys.stderr,
            )
            return 1

        args.output.parent.mkdir(parents=True, exist_ok=True)

        rng = random.Random()
        total_written = 0
        total_skipped = 0

        with args.output.open("a", encoding="utf-8") as output_file:
            def write_event(event: dict) -> None:
                output_file.write(json.dumps(event, separators=(",", ":")))
                output_file.write("\n")

            for _ in range(args.session_count):
                written, skipped = generate_session(
                    cursor, campus_id, args.session_length, rng, args.lookback_days, write_event
                )
                total_written += written
                total_skipped += skipped

        print(
            f"Wrote {total_written} event(s) across {args.session_count} session(s) to "
            f"'{args.output}' ({total_skipped} body event(s) skipped for lack of matching data)."
        )
        return 0
    except pyodbc.Error as e:
        print(f"Error: a database operation failed: {e}", file=sys.stderr)
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
