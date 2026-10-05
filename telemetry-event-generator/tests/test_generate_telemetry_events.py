"""Tests for generate_telemetry_events.py, run against a fake in-memory "database" and a fake
in-memory Kafka producer -- no live SQL Server or Kafka broker is required. See conftest.py for
the pyodbc stub and import-path setup this relies on.

Run with: pytest (from this component's root, or anywhere above it).

Covers:
  - normal session generation (SESSION_INIT, LOGIN, body events, LOGOUT; correct extra fields
    per event type; monotonically non-decreasing timestamps; JSON-serializable events)
  - the sparse-data skip path (a person with zero matching content/test/submission rows
    produces a session with only SESSION_INIT/LOGIN/LOGOUT and the rest counted as skipped)
  - get_eligible_course_ids / pick_* functions against the fake data directly
  - get_kafka_config's config-shape validation
  - build_write_event's three sink modes (kafka/file/both), including key/value encoding
  - main() end-to-end with a fake pyodbc connection and a fake KafkaProducer substituted in,
    covering the real CLI/argparse/config-loading/error-handling path, not just the inner
    generation functions

What this suite deliberately does NOT cover, because nothing reachable from this repo's CI (or
most contributors' machines) can: a real SQL Server connection, and a real Kafka broker actually
receiving a message. Those are exercised by hand against the `els-database` and `kafka`
components; see this component's CLAUDE.md for exactly what has and hasn't been verified live.
"""
import json
import random
import sys
import tempfile
import types
from datetime import datetime, timezone
from pathlib import Path

import generate_telemetry_events as gte

CAMPUS_ID = 1

# course_person rows: id -> (campus_id, course_id, person_id)
COURSE_PERSON = {
    1: (1, 100, 10),
    2: (1, 101, 10),
    3: (1, 100, 20),
    4: (1, 999, 30),  # person 30: enrolled only in a course with NO content/test/submission
}
COURSE_CONTENT = [  # (id, campus_id, course_id)
    (1000, 1, 100),
]
COURSE_TEST = [  # (id, campus_id, course_id)
    (2000, 1, 100),
]
SUBMISSION = [  # (id, campus_id, course_person_id, course_test_id)
    (3000, 1, 1, 2000),  # made by course_person 1 -> person 10, course 100
]


def row(**kwargs):
    return types.SimpleNamespace(**kwargs)


class FakeCursor:
    def __init__(self):
        self._result = None

    def execute(self, sql, *params):
        if "FROM els.campus WHERE uuid" in sql:
            (u,) = params
            # The CLI only accepts syntactically valid UUIDs (campus_uuid_type), so main()-level
            # tests pass a real-looking UUID; map it to the same fake campus as the short
            # sentinel the function-level tests below use directly.
            if u == "11111111-1111-1111-1111-111111111111":
                u = "campus-uuid-A"
            self._result = [row(id=CAMPUS_ID)] if u == "campus-uuid-A" else []
        elif "SELECT TOP (1) 1 AS hit FROM els.course_person" in sql:
            (campus_id,) = params
            hit = any(cp[0] == campus_id for cp in COURSE_PERSON.values())
            self._result = [row(hit=1)] if hit else []
        elif "SELECT TOP (1) person_id FROM els.course_person" in sql:
            (campus_id,) = params
            matches = [p for (c, _, p) in COURSE_PERSON.values() if c == campus_id]
            self._result = [row(person_id=random.choice(matches))] if matches else []
        elif "SELECT DISTINCT course_id FROM els.course_person" in sql:
            campus_id, person_id = params
            courses = sorted({
                course for (c, course, p) in COURSE_PERSON.values()
                if c == campus_id and p == person_id
            })
            self._result = [row(course_id=c) for c in courses]
        elif "FROM els.course_content" in sql:
            campus_id = params[0]
            course_ids = set(params[1:])
            matches = [
                row(id=i, course_id=c) for (i, camp, c) in COURSE_CONTENT
                if camp == campus_id and c in course_ids
            ]
            self._result = [random.choice(matches)] if matches else []
        elif "FROM els.course_test" in sql:
            campus_id = params[0]
            course_ids = set(params[1:])
            matches = [
                row(id=i, course_id=c) for (i, camp, c) in COURSE_TEST
                if camp == campus_id and c in course_ids
            ]
            self._result = [random.choice(matches)] if matches else []
        elif "FROM els.submission s" in sql:
            campus_id, person_id = params
            matches = []
            for (sid, camp, cpid, ctid) in SUBMISSION:
                cp = COURSE_PERSON.get(cpid)
                if camp == campus_id and cp and cp[2] == person_id:
                    matches.append(row(submission_id=sid, course_test_id=ctid, course_id=cp[1]))
            self._result = [random.choice(matches)] if matches else []
        else:
            raise AssertionError(f"unexpected SQL: {sql}")

    def fetchone(self):
        return self._result[0] if self._result else None

    def fetchall(self):
        return list(self._result)


def test_resolve_campus_id():
    c = FakeCursor()
    assert gte.resolve_campus_id(c, "campus-uuid-A") == CAMPUS_ID
    assert gte.resolve_campus_id(c, "does-not-exist") is None


def test_eligible_courses_and_pickers():
    c = FakeCursor()
    courses = gte.get_eligible_course_ids(c, CAMPUS_ID, 10)
    assert sorted(courses) == [100, 101]

    extra = gte.pick_content_access(c, CAMPUS_ID, courses)
    assert extra == {"course_id": 100, "course_content_id": 1000}

    extra = gte.pick_course_test(c, CAMPUS_ID, courses)
    assert extra == {"course_id": 100, "course_test_id": 2000}

    extra = gte.pick_submission(c, CAMPUS_ID, 10)
    assert extra == {"course_id": 100, "course_test_id": 2000, "submission_id": 3000}

    # Person 20 is enrolled in course 100 too, so they share its content/test, but have no
    # submission of their own (none of SUBMISSION was made via their course_person row).
    courses_20 = gte.get_eligible_course_ids(c, CAMPUS_ID, 20)
    assert courses_20 == [100]
    assert gte.pick_submission(c, CAMPUS_ID, 20) is None


def test_full_session_normal_person():
    c = FakeCursor()
    rng = random.Random(42)
    events = []
    written, skipped = gte.generate_session(
        c, CAMPUS_ID, session_length=20, rng=rng, lookback_days=0,
        write_event=events.append,
    )
    assert written == len(events)
    assert events[0]["event_type"] == "SESSION_INIT"
    assert events[1]["event_type"] == "LOGIN"
    assert events[-1]["event_type"] == "LOGOUT"

    # SESSION_INIT must NOT carry person_id -- the client doesn't know who's logging in yet.
    assert "person_id" not in events[0]
    assert set(events[0]) == {"event_id", "event_type", "session_id", "timestamp", "campus_id"}
    # Every other event, starting with LOGIN, does carry person_id.
    assert all("person_id" in e for e in events[1:])

    body = events[2:-1]
    assert all(e["event_type"] in gte.BODY_EVENT_TYPES for e in body)

    for e in body:
        if e["event_type"] == "CONTENT_ACCESS":
            assert set(e) == {"event_id", "event_type", "session_id", "timestamp",
                               "campus_id", "person_id", "course_id", "course_content_id"}
        elif e["event_type"] == "COURSE_TEST":
            assert set(e) == {"event_id", "event_type", "session_id", "timestamp",
                               "campus_id", "person_id", "course_id", "course_test_id"}
        elif e["event_type"] == "SUBMISSION":
            assert set(e) == {"event_id", "event_type", "session_id", "timestamp",
                               "campus_id", "person_id", "course_id", "course_test_id",
                               "submission_id"}

    # Every event shares the same session_id and (since this fake data has one person per
    # course_person draw) the same person_id; timestamps are non-decreasing.
    assert len({e["session_id"] for e in events}) == 1
    assert len({e["person_id"] for e in events[1:]}) == 1
    timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]
    assert timestamps == sorted(timestamps)
    assert all(t.tzinfo is not None for t in timestamps)

    # Every event round-trips through JSON cleanly (this is exactly what the real script
    # writes to the NDJSON file, one line per event).
    for e in events:
        json.loads(json.dumps(e))


def test_sparse_data_skips_without_retry(monkeypatch):
    c = FakeCursor()
    rng = random.Random(7)

    # Force the session onto person 30, who is only enrolled in course 999 -- a course with
    # no content, no test, and no submissions anywhere in the fake dataset.
    monkeypatch.setattr(gte, "pick_session_person", lambda cursor, campus_id: 30)

    events = []
    written, skipped = gte.generate_session(
        c, CAMPUS_ID, session_length=20, rng=rng, lookback_days=0,
        write_event=events.append,
    )

    assert written == 3  # SESSION_INIT, LOGIN, LOGOUT only
    assert skipped >= 1  # every attempted body event had nothing to match and was skipped
    assert [e["event_type"] for e in events] == ["SESSION_INIT", "LOGIN", "LOGOUT"]
    assert "person_id" not in events[0]
    assert all(e["person_id"] == 30 for e in events[1:])


def test_lookback_days_spreads_session_start_into_the_past():
    c = FakeCursor()
    rng = random.Random(1)
    events = []
    gte.generate_session(
        c, CAMPUS_ID, session_length=5, rng=rng, lookback_days=30,
        write_event=events.append,
    )
    session_start = datetime.fromisoformat(events[0]["timestamp"])
    now = datetime.now(timezone.utc)
    assert (now - session_start).total_seconds() > 0


def test_get_kafka_config_missing_section():
    try:
        gte.get_kafka_config({"sqlServer": {}, "auth": {}})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "no 'kafka' section" in str(e)


def test_get_kafka_config_missing_keys():
    try:
        gte.get_kafka_config({"kafka": {"bootstrapServers": "localhost:9092"}})
        assert False, "expected ValueError"
    except ValueError as e:
        assert "bootstrapServers" in str(e) and "topic" in str(e)


def test_get_kafka_config_happy_path():
    bootstrap, topic = gte.get_kafka_config(
        {"kafka": {"bootstrapServers": "localhost:9092", "topic": "telemetry-events"}}
    )
    assert bootstrap == "localhost:9092"
    assert topic == "telemetry-events"


class FakeDeliveryFuture:
    def __init__(self, raise_exc=None):
        self._raise_exc = raise_exc

    def get(self, timeout=None):
        if self._raise_exc is not None:
            raise self._raise_exc
        return None


class FakeKafkaProducer:
    """Duck-types just the KafkaProducer surface build_write_event()/main() actually use."""

    def __init__(self, *args, fail_delivery=False, **kwargs):
        self.sent = []  # list of (topic, key, value) tuples, as actually passed to send()
        self.closed = False
        self._fail_delivery = fail_delivery

    def send(self, topic, key=None, value=None):
        self.sent.append((topic, key, value))
        if self._fail_delivery:
            return FakeDeliveryFuture(raise_exc=gte.KafkaError("fake delivery failure"))
        return FakeDeliveryFuture()

    def partitions_for(self, topic):
        return {0, 1, 2}

    def close(self):
        self.closed = True


def test_build_write_event_file_only():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.ndjson"
        with path.open("a", encoding="utf-8") as f:
            write_event = gte.build_write_event("file", producer=None, topic=None, output_file=f)
            event = {"event_id": "e1", "event_type": "LOGIN", "session_id": "s1"}
            write_event(event)
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == event


def test_build_write_event_kafka_only():
    producer = FakeKafkaProducer()
    write_event = gte.build_write_event(
        "kafka", producer=producer, topic="telemetry-events", output_file=None
    )
    event = {"event_id": "e1", "event_type": "LOGIN", "session_id": "session-abc"}
    write_event(event)

    assert len(producer.sent) == 1
    topic, key, value = producer.sent[0]
    assert topic == "telemetry-events"
    assert key == b"session-abc"  # keyed by session_id, per the kafka component's design
    assert json.loads(value.decode("utf-8")) == event


def test_build_write_event_both_sinks_get_identical_content():
    producer = FakeKafkaProducer()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.ndjson"
        with path.open("a", encoding="utf-8") as f:
            write_event = gte.build_write_event(
                "both", producer=producer, topic="telemetry-events", output_file=f
            )
            event = {
                "event_id": "e1", "event_type": "SUBMISSION",
                "session_id": "session-xyz", "submission_id": 55,
            }
            write_event(event)

        file_event = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        _, key, value = producer.sent[0]
        kafka_event = json.loads(value.decode("utf-8"))
        assert file_event == kafka_event == event
        assert key == b"session-xyz"


def test_build_write_event_kafka_delivery_failure_propagates():
    producer = FakeKafkaProducer(fail_delivery=True)
    write_event = gte.build_write_event(
        "kafka", producer=producer, topic="telemetry-events", output_file=None
    )
    try:
        write_event({"event_id": "e1", "event_type": "LOGIN", "session_id": "s1"})
        assert False, "expected the fake delivery failure to propagate"
    except gte.KafkaError:
        pass


def test_main_end_to_end_both_sinks(monkeypatch):
    """Exercises the real CLI/argparse/config-loading/main() path (not just the inner generation
    functions), with only the two genuine externalities -- the database and the Kafka broker --
    replaced by fakes. Confirms the full wiring: config is read, both sinks receive the same
    events, the producer is closed afterward, and the summary/exit code are correct."""
    cursor = FakeCursor()

    class FakeConnection:
        def __init__(self):
            self.closed = False

        def cursor(self):
            return cursor

        def close(self):
            self.closed = True

    fake_connection = FakeConnection()
    monkeypatch.setattr(gte.pyodbc, "connect", lambda *a, **kw: fake_connection)

    producer_holder = {}

    def fake_producer_factory(*args, **kwargs):
        producer_holder["producer"] = FakeKafkaProducer(*args, **kwargs)
        return producer_holder["producer"]

    monkeypatch.setattr(gte, "KafkaProducer", fake_producer_factory)

    with tempfile.TemporaryDirectory() as tmp:
        config_path = Path(tmp) / "config.json"
        config_path.write_text(json.dumps({
            "sqlServer": {"host": "localhost", "database": "els_dev"},
            "auth": {"user": "sa", "password": "x"},
            "kafka": {"bootstrapServers": "localhost:9092", "topic": "telemetry-events"},
        }), encoding="utf-8")
        output_path = Path(tmp) / "events.ndjson"

        monkeypatch.setattr(sys, "argv", [
            "generate_telemetry_events.py",
            "--campus-uuid", "11111111-1111-1111-1111-111111111111",
            "--session-count", "2",
            "--session-length", "10",
            "--sink", "both",
            "--output", str(output_path),
            "--config-path", str(config_path),
            "--lookback-days", "0",
        ])

        exit_code = gte.main()

        assert exit_code == 0
        file_lines = output_path.read_text(encoding="utf-8").splitlines()
        producer = producer_holder["producer"]
        assert len(file_lines) == len(producer.sent)
        assert len(file_lines) > 0
        for line, (topic, key, value) in zip(file_lines, producer.sent):
            assert topic == "telemetry-events"
            assert json.loads(line) == json.loads(value.decode("utf-8"))
        assert fake_connection.closed
        assert producer.closed
