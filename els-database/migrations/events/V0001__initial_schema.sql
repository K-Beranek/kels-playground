------------------------------------------------------------------------------
--  Lookup tables
------------------------------------------------------------------------------
CREATE TABLE events.telemetry_event (
    id INT IDENTITY(1,1) NOT NULL,
    payload NVARCHAR(MAX) NOT NULL,
    row_inserted_time DATETIME2 NOT NULL,
    CONSTRAINT PK_telemetry_event PRIMARY KEY (id)
);
