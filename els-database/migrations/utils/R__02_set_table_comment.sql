-- Repeatable migration for the "utils" schema.
--
-- Thin wrapper: sets (or updates, if already set) the MS_Description extended property on a
-- table. All the actual logic -- existence checks, add-vs-update decision -- lives in
-- utils.set_extended_property; this procedure exists only to keep the call site down to the
-- three parameters that actually matter for a table comment, without callers ever passing an
-- explicit "no column" marker.
CREATE OR ALTER PROCEDURE utils.set_table_comment
    @schema_name SYSNAME,
    @table_name  SYSNAME,
    @comment     NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    EXEC utils.set_extended_property
        @schema_name = @schema_name,
        @table_name  = @table_name,
        @column_name = NULL,
        @comment     = @comment;
END;
