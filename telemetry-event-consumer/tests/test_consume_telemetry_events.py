import json

import pytest

import consume_telemetry_events as cte


# ---------------------------------------------------------------------------
# Fakes -- hand-written, duck-typing only the surface the code under test calls, matching
# telemetry-event-generator's established testing style (see its CLAUDE.md for the reasoning).
# ---------------------------------------------------------------------------


class FakeMessage:
    def __init__(self, value: bytes, partition: int = 0, offset: int = 0):
        self.value = value
        self.partition = partition
        self.offset = offset


class FakeCursor:
    def __init__(self, fail_on_call: int | None = None):
        self.executed = []  # list of (sql, params)
        self._fail_on_call = fail_on_call
        self._call_count = 0

    def execute(self, sql, params):
        self._call_count += 1
        if self._fail_on_call == self._call_count:
            raise cte.pyodbc.Error("simulated database error")
        self.executed.append((sql, params))


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.commit_count = 0
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commit_count += 1

    def close(self):
        self.closed = True


class FakeKafkaConsumer:
    """Stands in for kafka.KafkaConsumer: iterable over a fixed list of messages, tracks commits."""

    def __init__(self, messages):
        self._messages = messages
        self.committed_offsets = []  # one entry appended per successful consumer.commit() call
        self.closed = False

    def __iter__(self):
        return iter(self._messages)

    def commit(self):
        self.committed_offsets.append(len(self.committed_offsets))

    def close(self):
        self.closed = True


def make_fake_consumer_class(messages):
    """Builds a drop-in replacement for the KafkaConsumer class, pre-loaded with `messages`, so
    main()'s `KafkaConsumer(topic, **kwargs)` call returns a FakeKafkaConsumer instead of trying
    to reach a real broker."""

    def _constructor(topic, **kwargs):
        return FakeKafkaConsumer(messages)

    return _constructor


def make_event(event_type="LOGIN", session_id="s1") -> bytes:
    return json.dumps({"event_type": event_type, "session_id": session_id}).encode("utf-8")


# ---------------------------------------------------------------------------
# build_connection_string
# ---------------------------------------------------------------------------


def test_build_connection_string_host_port():
    sql_server = {
        "host": "host.docker.internal",
        "port": 1433,
        "instanceName": "",
        "database": "els_dev",
        "encrypt": True,
        "trustServerCertificate": True,
    }
    auth = {"user": "telemetry_consumer", "password": "secret"}

    conn_str = cte.build_connection_string(sql_server, auth)

    assert "SERVER=host.docker.internal,1433;" in conn_str
    assert "DATABASE=els_dev;" in conn_str
    assert "UID=telemetry_consumer;" in conn_str
    assert "PWD=secret;" in conn_str
    assert "Encrypt=yes;" in conn_str
    assert "TrustServerCertificate=yes;" in conn_str


def test_build_connection_string_instance_name_overrides_port():
    sql_server = {
        "host": "KB-NB-2023",
        "port": 1433,
        "instanceName": "SQLEXPRESS",
        "database": "els_dev",
        "encrypt": False,
        "trustServerCertificate": False,
    }
    auth = {"user": "sa", "password": "pw"}

    conn_str = cte.build_connection_string(sql_server, auth)

    assert "SERVER=KB-NB-2023\\SQLEXPRESS;" in conn_str
    assert ",1433" not in conn_str
    assert "Encrypt=no;" in conn_str
    assert "TrustServerCertificate=no;" in conn_str


# ---------------------------------------------------------------------------
# describe_for_log
# ---------------------------------------------------------------------------


def test_describe_for_log_valid_json():
    payload = make_event("LOGIN", "abc-123")
    assert cte.describe_for_log(payload) == "LOGIN session=abc-123"


def test_describe_for_log_invalid_json_falls_back():
    payload = b"not json at all"
    description = cte.describe_for_log(payload)
    assert "unparseable payload" in description


# ---------------------------------------------------------------------------
# consume_forever
# ---------------------------------------------------------------------------


def test_consume_forever_happy_path_inserts_and_commits_each_message():
    messages = [
        FakeMessage(make_event("LOGIN", "s1"), partition=0, offset=10),
        FakeMessage(make_event("LOGOUT", "s1"), partition=0, offset=11),
    ]
    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    consumer = FakeKafkaConsumer(messages)

    cte.consume_forever(consumer, connection)

    assert len(cursor.executed) == 2
    sql, params = cursor.executed[0]
    assert "INSERT INTO events.telemetry_event" in sql
    assert params == messages[0].value.decode("utf-8")
    assert cursor.executed[1][1] == messages[1].value.decode("utf-8")

    assert connection.commit_count == 2
    assert len(consumer.committed_offsets) == 2


def test_consume_forever_db_failure_stops_without_committing_that_offset():
    messages = [
        FakeMessage(make_event("LOGIN", "s1"), offset=10),
        FakeMessage(make_event("LOGOUT", "s1"), offset=11),
    ]
    # Fail on the 2nd cursor.execute() call (the 2nd message).
    cursor = FakeCursor(fail_on_call=2)
    connection = FakeConnection(cursor)
    consumer = FakeKafkaConsumer(messages)

    with pytest.raises(cte.pyodbc.Error):
        cte.consume_forever(consumer, connection)

    # First message: written and both commits happened.
    assert len(cursor.executed) == 1
    assert connection.commit_count == 1
    assert len(consumer.committed_offsets) == 1


# ---------------------------------------------------------------------------
# main() -- config validation and a full faked-out end-to-end run
# ---------------------------------------------------------------------------


def write_config(tmp_path, kafka_section=None, sql_server_overrides=None):
    config = {
        "sqlServer": {
            "host": "host.docker.internal",
            "port": 1433,
            "instanceName": "",
            "database": "els_dev",
            "encrypt": True,
            "trustServerCertificate": True,
        },
        "auth": {"user": "telemetry_consumer", "password": "secret"},
    }
    if sql_server_overrides:
        config["sqlServer"].update(sql_server_overrides)
    if kafka_section is not None:
        config["kafka"] = kafka_section

    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return str(config_path)


def test_main_missing_config_file_exits_clearly(monkeypatch, tmp_path):
    missing_path = str(tmp_path / "does_not_exist.json")
    monkeypatch.setattr("sys.argv", ["consume_telemetry_events.py", "--config-path", missing_path])

    with pytest.raises(SystemExit) as exc_info:
        cte.main()

    assert "config.template.json" in str(exc_info.value)


def test_main_missing_kafka_section_exits_clearly(monkeypatch, tmp_path):
    config_path = write_config(tmp_path, kafka_section=None)
    monkeypatch.setattr("sys.argv", ["consume_telemetry_events.py", "--config-path", config_path])

    with pytest.raises(SystemExit) as exc_info:
        cte.main()

    assert "kafka" in str(exc_info.value)


def test_main_missing_kafka_subkey_exits_clearly(monkeypatch, tmp_path):
    config_path = write_config(
        tmp_path, kafka_section={"bootstrapServers": "broker:19092", "topic": "telemetry-events"}
    )
    monkeypatch.setattr("sys.argv", ["consume_telemetry_events.py", "--config-path", config_path])

    with pytest.raises(SystemExit) as exc_info:
        cte.main()

    assert "groupId" in str(exc_info.value)


def test_main_end_to_end_happy_path(monkeypatch, tmp_path):
    messages = [FakeMessage(make_event("LOGIN", "s1"), offset=0)]
    config_path = write_config(
        tmp_path,
        kafka_section={
            "bootstrapServers": "broker:19092",
            "topic": "telemetry-events",
            "groupId": "telemetry-event-consumer",
        },
    )
    monkeypatch.setattr("sys.argv", ["consume_telemetry_events.py", "--config-path", config_path])
    monkeypatch.setattr(cte, "KafkaConsumer", make_fake_consumer_class(messages))

    cursor = FakeCursor()
    connection = FakeConnection(cursor)
    monkeypatch.setattr(cte.pyodbc, "connect", lambda conn_str: connection)

    cte.main()

    assert len(cursor.executed) == 1
    assert connection.commit_count == 1
    assert connection.closed is True
