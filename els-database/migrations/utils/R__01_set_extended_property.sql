-- Repeatable migration for the "utils" schema.
--
-- Engine procedure behind utils.set_table_comment / utils.set_column_comment. Not meant to be
-- called directly from outside this schema -- it takes a @column_name that may or may not be
-- NULL and branches accordingly, which is exactly the kind of "one extra parameter changes the
-- meaning of the call" shape the two wrapper procedures exist to hide.
--
-- What it does, every time it runs:
--   1. Confirm @schema_name.@table_name actually exists (OBJECT_ID lookup). If not, THROW.
--   2. If @column_name was given, confirm that column exists on the table (sys.columns lookup).
--      If not, THROW. This also gives us the column's column_id, which extended properties use
--      as "minor_id" instead of a name.
--   3. Check sys.extended_properties for an existing 'MS_Description' property on this exact
--      target (table, or table+column). If found, sp_updateextendedproperty; if not,
--      sp_addextendedproperty. This is what makes the whole thing idempotent: callers never need
--      to know or care whether a comment was already set.
--
-- Numbered "01" only to hint at read order for a human -- it has no effect on execution order.
-- SQL Server resolves procedure bodies at execution time (deferred name resolution), so this
-- procedure could reference utils.set_table_comment before that procedure exists and still work,
-- as long as both exist by the time anything is actually called. Flyway itself runs repeatable
-- migrations in alphabetical order of the part after "R__", which is why "01/02/03" was chosen
-- over, say, "engine/table/column" -- it happens to also sort in dependency order, but that's a
-- readability nicety here, not a requirement.
CREATE OR ALTER PROCEDURE utils.set_extended_property
    @schema_name SYSNAME,
    @table_name  SYSNAME,
    @column_name SYSNAME = NULL,
    @comment     NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @object_id INT = OBJECT_ID(QUOTENAME(@schema_name) + N'.' + QUOTENAME(@table_name));
    DECLARE @comment_as_variant SQL_VARIANT = CAST(CAST(@comment AS NVARCHAR(4000)) AS SQL_VARIANT)

    IF @object_id IS NULL
    BEGIN
        DECLARE @table_error NVARCHAR(2048) = FORMATMESSAGE(
            N'utils.set_extended_property: table %s.%s does not exist.',
            @schema_name, @table_name);
        THROW 50000, @table_error, 1;
    END;

    DECLARE @level2type NVARCHAR(128) = NULL;
    DECLARE @level2name SYSNAME       = NULL;
    DECLARE @minor_id   INT           = 0;

    IF @column_name IS NOT NULL
    BEGIN
        DECLARE @column_id INT = (
            SELECT column_id FROM sys.columns
            WHERE object_id = @object_id AND name = @column_name
        );

        IF @column_id IS NULL
        BEGIN
            DECLARE @column_error NVARCHAR(2048) = FORMATMESSAGE(
                N'utils.set_extended_property: column %s does not exist on table %s.%s.',
                @column_name, @schema_name, @table_name);
            THROW 50000, @column_error, 1;
        END;

        SET @level2type = N'COLUMN';
        SET @level2name = @column_name;
        SET @minor_id   = @column_id;
    END;

    IF EXISTS (
        SELECT 1 FROM sys.extended_properties
        WHERE major_id = @object_id
          AND minor_id = @minor_id
          AND class    = 1 -- 1 = "object or column" -- covers both the table itself (minor_id 0) and a column on it
          AND name     = N'MS_Description'
    )
    BEGIN
        EXEC sys.sp_updateextendedproperty
            @name       = N'MS_Description',
            @value      = @comment_as_variant,
            @level0type = N'SCHEMA', @level0name = @schema_name,
            @level1type = N'TABLE',  @level1name = @table_name,
            @level2type = @level2type, @level2name = @level2name;
    END
    ELSE
    BEGIN
        EXEC sys.sp_addextendedproperty
            @name       = N'MS_Description',
            @value      = @comment_as_variant,
            @level0type = N'SCHEMA', @level0name = @schema_name,
            @level1type = N'TABLE',  @level1name = @table_name,
            @level2type = @level2type, @level2name = @level2name;
    END;
END;
