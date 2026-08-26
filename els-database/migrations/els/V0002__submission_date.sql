ALTER TABLE els.submission ADD submitted_time DATETIME2 NULL;
GO

UPDATE els.submission
SET    submitted_time = '2026-08-25T00:00:00'
WHERE  submitted_time IS NULL;
GO

ALTER TABLE els.submission ALTER COLUMN submitted_time DATETIME2 NOT NULL;
GO

EXECUTE utils.set_column_comment @schema_name = N'els', @table_name = N'submission', @column_name = N'submitted_time', @comment = N'Date and time the submission was made.';
