------------------------------------------------------------------------------
--  Course
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
desired_record_count AS (
    SELECT (20 + '{complexity}' / 2) AS max_row_num),
sp_fragment_1 AS (
    SELECT code, name
     FROM   (VALUES ('01', 'Practical'), ('02', 'Theoretical'), ('03', 'Metaphysical'), ('04', 'Spherical'), ('05', 'Vestibular'), ('06', 'Functional'), ('07', 'Residual'), ('08', 'Cross-discipline')) AS src(code, name)),
sp_fragment_2 AS (
    SELECT code, name
    FROM   (VALUES ('01', NULL), ('02', 'and Unorthodox'), ('03', 'and Speculative'), ('04', 'Thorough'), ('05', 'Contemporary'), ('06', 'Historical')) AS src(code, name)),
sp_fragment_3 AS (
    SELECT code, name
    FROM   (VALUES ('01', 'Analysis'), ('02', 'Research'), ('03', 'Evaluation'), ('04', 'Insights'), ('05', 'Decomposition')) AS src(code, name)),
sp_fragment_4 AS (
    SELECT code, name
    FROM   (VALUES ('01', 'of Software'), ('02', 'in 21st century'), ('03', 'of Edible stuff'), ('04', 'of unimportant things'), ('05', 'of Modern Art')) AS src(code, name)),
generated_data AS (
    SELECT
        c.id AS campus_id,
        concat_ws('', 'C', sp1.code, sp2.code, sp3.code, sp4.code) AS course_number,
        concat_ws(' ', sp1.name, sp2.name, sp3.name, sp4.name) AS name,
        'Synthetic Course' AS description,
        row_number() OVER (ORDER BY checksum(newid())) AS row_num
    FROM
       campus AS c
       CROSS JOIN sp_fragment_1 AS sp1
       CROSS JOIN sp_fragment_2 AS sp2
       CROSS JOIN sp_fragment_3 AS sp3
       CROSS JOIN sp_fragment_4 AS sp4)
INSERT INTO els.course (
    campus_id,
    course_type,
    name,
    course_number,
    description
)
SELECT
    gd.campus_id,
    ct.code AS course_type,
    gd.name,
    gd.course_number,
    gd.description
FROM
    generated_data AS gd
    CROSS JOIN desired_record_count AS drc
    INNER JOIN els.course_type AS ct
       ON ct.sort_order = 1 + abs(checksum(gd.course_number) % 3)
WHERE  gd.row_num <= drc.max_row_num;


/*
    Course
    Course Contents
    Course Test

    Course Person
    Term Course
    Submission
*/