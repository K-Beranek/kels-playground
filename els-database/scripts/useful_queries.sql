------------------------------------------------------------------------------
-- Query list of tables in the database and estimate on number of rows in them
SELECT
	SCHEMA_NAME(t.[schema_id]) AS [table_schema],
	OBJECT_NAME(p.[object_id]) AS [table_name],
	SUM(p.[rows]) AS [row_count]
FROM [sys].[partitions] p
    INNER JOIN [sys].[tables] t
		ON p.[object_id] = t.[object_id]
WHERE p.[index_id] < 2
GROUP BY p.[object_id], t.[schema_id]
ORDER BY 1, 2 ASC

------------------------------------------------------------------------------
-- To get rid of unwanted data
delete from els.submission where campus_id = -1;
delete from els.course_person where campus_id = -1;
delete from els.course_test where campus_id = -1;
delete from els.course_content where campus_id = -1;
delete from els.term_course where campus_id = -1;
delete from els.course where campus_id = -1;
delete from els.person where campus_id = -1;
delete from els.term where campus_id = -1;
delete from els.semester where campus_id = -1;
delete from els.study_program where campus_id = -1;
delete from els.campus where id = -1;
