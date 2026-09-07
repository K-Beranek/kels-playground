ALTER TABLE els.term ADD academic_year INT NULL;
GO

UPDATE els.term
SET
	academic_year = src.ay
FROM
	(
	SELECT
		campus_id,
		id,
		2025 + ROW_NUMBER() OVER (PARTITION BY campus_id, study_program_id, semester_type ORDER BY id DESC) AS ay
	FROM
		els.term
	) src
WHERE
	term.campus_id = src.campus_id
	and term.id = src.id
GO

ALTER TABLE els.term ALTER COLUMN academic_year INT NOT NULL;
GO

EXEC utils.set_column_comment @schema_name = N'els', @table_name = N'term', @column_name = N'academic_year', @comment = N'Academic year this semester falls in (e.g. 2026).';
GO
