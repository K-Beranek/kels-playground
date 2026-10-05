CREATE TABLE events.telemetry_event (
    id INT IDENTITY(1,1) NOT NULL,
    payload NVARCHAR(MAX) NOT NULL,
    row_inserted_time DATETIME2 NOT NULL,
    CONSTRAINT PK_telemetry_event PRIMARY KEY (id)
);

EXEC utils.set_table_comment
    @schema_name = 'events',
    @table_name = 'telemetry_event',
    @comment = 'Raw telemetry landing table, written by telemetry-event-consumer. Append-only; payload is the exact JSON bytes received from Kafka, unparsed. See docs/telemetry-event-consumer.md.';

EXEC utils.set_column_comment
    @schema_name = 'events',
    @table_name = 'telemetry_event',
    @column_name = 'payload',
    @comment = 'Raw JSON as received from Kafka (one telemetry-events message value) -- not parsed or typed here.';

EXEC utils.set_column_comment
    @schema_name = 'events',
    @table_name = 'telemetry_event',
    @column_name = 'row_inserted_time',
    @comment = 'Ingestion time (when the consumer wrote this row) -- not event time. The event''s own timestamp is already inside payload.';

----------------------------------------------------------------
GRANT INSERT ON events.telemetry_event TO telemetry_consumer;
