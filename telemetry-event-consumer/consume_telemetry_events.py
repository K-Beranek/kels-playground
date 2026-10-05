"""Reads telemetry events from the kafka component's telemetry-events topic and writes each one,
verbatim, into els-database's events.telemetry_event landing table.

Third and last part of the generator -> kafka -> SQL Server pipeline. This script is deliberately
a pure sink: it does not parse, validate, or reshape the event payload -- it stores exactly the
JSON bytes Kafka delivered, and stamps each row with ingestion time (when this consumer wrote it),
not event time (which is already inside the payload itself; see README.md). Any parsing/typing of
individual event fields is left to whatever reads events.telemetry_event next (e.g. els_transform).

Runs as a long-lived process (see docker-compose.yml), not a one-shot batch job: it stays connected
to Kafka and writes rows as messages arrive, the idiomatic way to consume from Kafka. There is no
--sink-style choice here the way the generator has one -- this component exists specifically to be
the Kafka-to-SQL-Server leg of the pipeline, so there is only one thing for it to do.

Usage:
    python consume_telemetry_events.py [--config-path config/config.json]

See CLAUDE.md for the delivery-semantics trade-off (at-least-once, duplicates possible on crash,
deliberately left unaddressed for now) and why offsets are committed manually, after the database
write succeeds, rather than left on Kafka's auto-commit default.
"""
import argparse
import json
import signal
import sys

import pyodbc
from kafka import KafkaConsumer
from kafka.errors import KafkaError

# Matches the kafka component's pinned apache/kafka:4.1.2 -- see CLAUDE.md for why this is set
# explicitly rather than left to kafka-python's default auto-detection. That non-fail-fast gap was
# found and verified on the producer side (telemetry-event-generator); it has not been re-verified
# here against a live broker, but KafkaConsumer shares the same underlying client code that caused
# it, so the same explicit setting is applied defensively rather than waiting to rediscover the bug.
KAFKA_API_VERSION = (4, 1, 2)
KAFKA_REQUEST_TIMEOUT_MS = 10_000

# The only ODBC driver this script will ever run against: unlike telemetry-event-generator (which
# runs natively on whatever machine Karel is using, hence its --odbc-driver flag), this component
# only ever runs inside the Docker image built by this folder's own Dockerfile, which installs
# exactly one driver version. One less thing to make configurable since there is truly only one
# correct value here.
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_connection_string(sql_server: dict, auth: dict) -> str:
    if sql_server.get("instanceName"):
        server_part = f"{sql_server['host']}\\{sql_server['instanceName']}"
    else:
        server_part = f"{sql_server['host']},{sql_server['port']}"

    encrypt = "yes" if sql_server.get("encrypt", True) else "no"
    trust_cert = "yes" if sql_server.get("trustServerCertificate", False) else "no"

    return (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER={server_part};"
        f"DATABASE={sql_server['database']};"
        f"UID={auth['user']};"
        f"PWD={auth['password']};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
    )


def describe_for_log(payload_bytes: bytes) -> str:
    """Best-effort one-line description of a message for console logging only -- never used for
    anything stored. If the payload isn't parseable JSON (shouldn't happen, but this is a log
    line, not the insert path), falls back to a truncated raw preview rather than raising."""
    try:
        event = json.loads(payload_bytes)
        event_type = event.get("event_type", "?")
        session_id = event.get("session_id", "?")
        return f"{event_type} session={session_id}"
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        preview = payload_bytes[:80]
        return f"<unparseable payload, first 80 bytes: {preview!r}>"


def consume_forever(consumer: KafkaConsumer, connection: pyodbc.Connection) -> None:
    cursor = connection.cursor()
    insert_sql = (
        "INSERT INTO events.telemetry_event (payload, row_inserted_time) "
        "VALUES (?, SYSUTCDATETIME())"
    )

    for message in consumer:
        payload_bytes = message.value
        print(
            f"[partition {message.partition} offset {message.offset}] "
            f"{describe_for_log(payload_bytes)}",
            flush=True,
        )

        payload_str = payload_bytes.decode("utf-8")

        try:
            cursor.execute(insert_sql, payload_str)
            connection.commit()
        except pyodbc.Error:
            # Fail loud, no retry, no silent skip -- the same "stop immediately on a write
            # failure" convention already used by generate_telemetry_events.py and
            # generate_synthetic_data.py. The offset for *this* message is not committed, so
            # under docker-compose's restart policy the container restarts and this message gets
            # redelivered -- the known, accepted at-least-once/duplicate-on-crash trade-off (see
            # CLAUDE.md); a message that succeeded earlier in this same loop is not redelivered,
            # since its offset was already committed below.
            print(
                f"Database write failed for partition {message.partition} "
                f"offset {message.offset} -- stopping.",
                file=sys.stderr,
            )
            raise

        consumer.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-path",
        default="config/config.json",
        help="Path to the JSON config file (default: config/config.json).",
    )
    args = parser.parse_args()

    try:
        config = load_config(args.config_path)
    except FileNotFoundError:
        sys.exit(
            f"Config file not found at '{args.config_path}'. Copy config/config.template.json "
            "to config/config.json and fill in real values first."
        )

    kafka_config = config.get("kafka")
    if not kafka_config:
        sys.exit(
            "config file has no 'kafka' section -- see config/config.template.json for the "
            "expected shape."
        )
    bootstrap_servers = kafka_config.get("bootstrapServers")
    topic = kafka_config.get("topic")
    group_id = kafka_config.get("groupId")
    if not bootstrap_servers or not topic or not group_id:
        sys.exit(
            "config's 'kafka' section must have 'bootstrapServers', 'topic', and 'groupId' all set."
        )

    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            # Pipeline's third stage is meant to land everything that was ever produced, not just
            # whatever shows up after this consumer first connects -- the opposite default from a
            # dashboard-style consumer that only cares about "from now on."
            auto_offset_reset="earliest",
            # Commit manually, only after a row is actually written (see consume_forever) --
            # Kafka's auto-commit default would mark a message "done" before we know the database
            # write succeeded, which risks silently losing events on a crash rather than merely
            # risking the (accepted) duplicate-on-crash trade-off this design already lives with.
            enable_auto_commit=False,
            api_version=KAFKA_API_VERSION,
            request_timeout_ms=KAFKA_REQUEST_TIMEOUT_MS,
        )
    except KafkaError as exc:
        sys.exit(f"Could not connect to Kafka at '{bootstrap_servers}': {exc}")

    connection_string = build_connection_string(config["sqlServer"], config["auth"])
    try:
        connection = pyodbc.connect(connection_string)
    except pyodbc.Error as exc:
        consumer.close()
        sys.exit(f"Could not connect to SQL Server: {exc}")

    print(
        f"Consuming topic '{topic}' as group '{group_id}' from {bootstrap_servers}, "
        f"writing into events.telemetry_event. Ctrl+C / SIGTERM to stop.",
        flush=True,
    )

    # Docker sends SIGTERM on `docker compose down`/`docker stop` -- raising SystemExit from the
    # handler lets the same try/finally below close the consumer and connection cleanly instead
    # of the process being killed mid-write.
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    try:
        consume_forever(consumer, connection)
    except (KeyboardInterrupt, SystemExit):
        print("Shutting down.", flush=True)
    finally:
        consumer.close()
        connection.close()


if __name__ == "__main__":
    main()
