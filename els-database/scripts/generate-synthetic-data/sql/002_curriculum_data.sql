------------------------------------------------------------------------------
--  Semester - four records, years 2026 and 2027, each with WINTER and SUMMER semesters
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
academic_years AS (
    SELECT academic_year
    FROM   (VALUES (2026), (2027)) AS src(academic_year))
INSERT INTO els.semester (
    campus_id,
    semester_type,
    academic_year,
    code
)
SELECT
    c.id AS campus_id,
    st.code AS semester_type,
    ay.academic_year AS academic_year,
    ay.academic_year || '/' || st.code AS code
FROM
    campus AS c
    CROSS JOIN els.semester_type AS st
    CROSS JOIN academic_years AS ay;

------------------------------------------------------------------------------
--  Study Program
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
desired_record_count AS (
    SELECT (3 + '{complexity}' / 80) AS max_row_num),
sp_fragment_1 AS (
    SELECT code, name
    FROM   (VALUES ('01', 'Applied'), ('02', 'Modern'), ('03', 'History of'), ('04', 'Cross-discipline'), ('05', 'Contemporary')) AS src(code, name)),
sp_fragment_2 AS (
    SELECT code, name
    FROM   (VALUES ('01', NULL), ('02', 'European'), ('03', 'American'), ('04', 'African'), ('05', 'Asian'), ('06', 'Australian')) AS src(code, name)),
sp_fragment_3 AS (
    SELECT code, name
    FROM   (VALUES ('01', 'Physics'), ('02', 'Literature'), ('03', 'Medicine'), ('04', 'Informatics'), ('05', 'Accoustics')) AS src(code, name)),
sp_fragment_4 AS (
    SELECT code, name
    FROM   (VALUES ('01', NULL), ('02', 'of 21st century'), ('03', 'of negligible significancy'), ('04', 'of 20th century'), ('05', 'in modern art')) AS src(code, name)),
generated_data AS (
    SELECT
        c.id AS campus_id,
        concat_ws('', 'SP', sp1.code, sp2.code, sp3.code, sp4.code) AS code,
        concat_ws(' ', sp1.name, sp2.name, sp3.name, sp4.name) AS name,
        'Synthetic Study Program' AS description,
        row_number() OVER (ORDER BY checksum(newid())) AS row_num
    FROM
        campus AS c
        CROSS JOIN sp_fragment_1 AS sp1
        CROSS JOIN sp_fragment_2 AS sp2
        CROSS JOIN sp_fragment_3 AS sp3
        CROSS JOIN sp_fragment_4 AS sp4)
INSERT INTO els.study_program (
    campus_id,
    code,
    name,
    description
)
SELECT
    gd.campus_id,
    gd.code,
    gd.name,
    gd.description
FROM
    generated_data AS gd
    CROSS JOIN desired_record_count AS drc
WHERE
    gd.row_num <= drc.max_row_num;

------------------------------------------------------------------------------
--  Term
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}')
INSERT INTO els.term (
    campus_id,
    study_program_id,
    semester_id
)
SELECT
    c.id AS campus_id,
    sp.id AS study_program_id,
    sem.id AS semester_id
FROM
    campus AS c
    INNER JOIN els.study_program AS sp
        ON sp.campus_id = c.id
    INNER JOIN els.semester AS sem
        ON sem.campus_id = c.id;
