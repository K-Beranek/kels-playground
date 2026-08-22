-- Repeatable migration for the "utils" schema.
--
-- Thin wrapper: sets (or updates, if already set) the MS_Description extended property on a
-- single column. Same reasoning as utils.set_table_comment -- utils.set_extended_property does
-- the real work, this just supplies @column_name so the caller doesn't have to think about the
-- shared procedure's NULL-means-table-level convention.
CREATE OR ALTER PROCEDURE utils.set_column_comment
    @schema_name SYSNAME,
    @table_name  SYSNAME,
    @column_name SYSNAME,
    @comment     NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    EXEC utils.set_extended_property
        @schema_name = @schema_name,
        @table_name  = @table_name,
        @column_name = @column_name,
        @comment     = @comment;
END;
