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

------------------------------------------------------------------------------
--  Course Contents
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
content_types AS (
    SELECT
        ct.code as content_type,
        series.value as row_number
    FROM els.course_content_type AS ct
    CROSS JOIN GENERATE_SERIES(1, 20) AS series
),
content_limits AS (
    SELECT
        campus_id,
        id,
        1 as max_introduction,
        7 + abs(checksum(newid())) % 8 as max_lecture,
        1 + abs(checksum(newid())) % 5 as max_announcement
    FROM els.course c
),
generated_data AS (
    SELECT
        c.id AS campus_id,
        crs.id AS course_id,
        ct.content_type AS content_type,
        ct.row_number AS row_number,
        max_introduction,
        max_lecture,
        max_announcement
    FROM
        campus AS c
        INNER JOIN content_limits crs
            ON c.id = crs.campus_id
        CROSS JOIN content_types ct
    WHERE
        ct.row_number <= CASE ct.content_type WHEN 'INTRODUCTION' THEN crs.max_introduction WHEN 'LECTURE' THEN crs.max_lecture WHEN 'ANNOUNCEMENT' THEN crs.max_announcement ELSE 0 END
)
INSERT INTO els.course_content (
    campus_id,
    course_id,
    content_type,
    ordering_position,
    active,
    document_text
)
SELECT
    campus_id,
    course_id,
    content_type,
    row_number,
    1 AS active,
    N'Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.' AS document_text
FROM
    generated_data AS gd;

------------------------------------------------------------------------------
--  Course Test
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
test_numbers AS (
    SELECT value as test_number
    FROM GENERATE_SERIES(1, 10)
),
content_limits AS (
    SELECT
        campus_id,
        id,
        0 + abs(checksum(CONCAT(campus_id, name))) % 8 as max_tests
    FROM els.course c
),
generated_data AS (
    SELECT
        c.id AS campus_id,
        crs.id AS course_id,
        crs.max_tests,
        tn.test_number
    FROM
        campus AS c
        INNER JOIN content_limits crs
            ON c.id = crs.campus_id
        CROSS JOIN test_numbers tn
    WHERE
        tn.test_number <= crs.max_tests
)
INSERT INTO els.course_test (
    campus_id,
    course_id,
    code,
    active,
    test_questions,
    possible_score,
    required_score
)
SELECT
    campus_id,
    course_id,
    'TEST_' || test_number AS code,
    1 AS active,
    N'Can you read Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua?' AS test_questions,
    20 + 10 * (abs(checksum(CONCAT(campus_id, max_tests, test_number))) % 20) AS possible_score,
    20 + 6 * (abs(checksum(CONCAT(campus_id, max_tests, test_number))) % 20) AS required_score
FROM
    generated_data AS gd;

------------------------------------------------------------------------------
--  Course Person
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
course_limits AS (
    SELECT
        campus_id,
        id,
        5 + abs(checksum(CONCAT(campus_id, name))) % 100 as max_students,
        1 + abs(checksum(CONCAT(campus_id, name))) % 4 as max_instructors
    FROM els.course c
),
generated_data AS (
    SELECT
        c.id AS campus_id,
        crs.id AS course_id,
        p.id AS person_id,
        crs.max_students,
        crs.max_instructors,
        row_number() OVER (PARTITION BY c.id, crs.id ORDER BY checksum(CONCAT(c.id, crs.id, p.id, p.first_name))) AS row_num 
    FROM
        campus AS c
        INNER JOIN course_limits crs
            ON c.id = crs.campus_id
        INNER JOIN els.person p
            ON c.id = p.campus_id
)
INSERT INTO els.course_person (
    campus_id,
    course_id,
    person_id,
    course_role
)
SELECT
    campus_id,
    course_id,
    person_id,
    CASE WHEN row_num = 1 THEN 'OWNER' WHEN row_num <= max_instructors + 1 THEN 'INSTRUCTOR' ELSE 'STUDENT' END AS course_role
FROM
    generated_data AS gd
WHERE
    row_num <= max_students + max_instructors + 1;

------------------------------------------------------------------------------
--  Term Course
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
generated_data AS (
    SELECT
        c.id AS campus_id,
        crs.id AS course_id,
        t.id AS term_id,
        CASE abs(checksum(CONCAT(c.id, crs.id, crs.name, t.id))) % 2 WHEN 0 THEN 'MANDATORY' ELSE 'OPTIONAL' END AS curriculum_type,
        row_number() OVER (PARTITION BY c.id, crs.id ORDER BY checksum(CONCAT(c.id, crs.id, t.id))) AS row_num 
    FROM
        campus AS c
        INNER JOIN els.course crs
            ON c.id = crs.campus_id
        INNER JOIN els.term t
            ON c.id = t.campus_id
)
INSERT INTO els.term_course (
    campus_id,
    course_id,
    term_id,
    curriculum_type
)
SELECT
    campus_id,
    course_id,
    term_id,
    curriculum_type
FROM
    generated_data AS gd
WHERE
    row_num <= 1;

------------------------------------------------------------------------------
--  Submission
------------------------------------------------------------------------------
WITH campus AS (
    SELECT id
    FROM   els.campus
    WHERE  code = '{campus_code}'),
attempt_numbers AS (
    SELECT value as attempt_number
    FROM GENERATE_SERIES(1, 5)),
generated_data AS (
    SELECT
        c.id AS campus_id,
        cp.id AS course_person_id,
        ct.id AS course_test_id,
        greatest(0, abs(checksum(CONCAT(cp.id, ct.id))) % 5 - abs(checksum(CONCAT(cp.id, ct.id))) % 2) AS max_attempts,
        an.attempt_number,
        abs(checksum(CONCAT(cp.id, ct.id, an.attempt_number))) % ct.possible_score as score,
        dateadd(second, -abs(checksum(CONCAT(cp.id, ct.id, an.attempt_number))) % (100 * 24 * 3600), CURRENT_TIMESTAMP) submitted_time
    FROM
        campus AS c
        INNER JOIN els.course_person cp
            ON c.id = cp.campus_id
        INNER JOIN els.course_test ct
            ON cp.campus_id = ct.campus_id
            AND cp.course_id = ct.course_id
        CROSS JOIN attempt_numbers an
    WHERE
        cp.course_role = 'STUDENT'
)
INSERT INTO els.submission (
    campus_id,
    course_person_id,
    course_test_id,
    submission_text,
    attempt_number,
    score,
    submitted_time
)
SELECT
    campus_id,
    course_person_id,
    course_test_id,
    CONCAT('Submission from ', course_person_id, ' for test ', course_test_id, ', attempt ', attempt_number) AS submission_text,
    attempt_number,
    score,
    submitted_time
FROM
    generated_data AS gd
WHERE
    attempt_number <= max_attempts;
