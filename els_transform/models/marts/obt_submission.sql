{{ config(materialized='view') }}

select
    s.submission_fact_key,
	campus.code AS campus_code,
	c.academic_year,
	c.semester_type,
	c.study_program_name,
	c.curriculum_type,
	c.course_dim_key,
	c.name AS course_name,
	ct.test_questions,
	cp.first_name,
	cp.last_name,
	cp.person_uuid,
	ct.possible_score,
	ct.required_score,
	s.attempt_number,
	s.score,
	s.submitted_time
from
	{{ ref('fact_submission') }} s
	LEFT JOIN {{ ref('dim_campus') }} campus
		ON campus.campus_dim_key = s.campus_dim_key
	LEFT JOIN {{ ref('dim_course') }} c
		ON c.course_dim_key = s.course_dim_key
	LEFT JOIN {{ ref('dim_course_person') }} cp
		ON cp.course_person_dim_key = s.course_person_dim_key
	LEFT JOIN {{ ref('dim_course_test') }} ct
		ON ct.course_test_dim_key = s.course_test_dim_key
