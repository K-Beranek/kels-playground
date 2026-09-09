select
	s.id AS submission_id,
	{{ dbt_utils.generate_surrogate_key(['s.campus_id', 's.id']) }} as submission_fact_key,
	{{ dbt_utils.generate_surrogate_key(['s.campus_id']) }} as campus_dim_key,
	{{ dbt_utils.generate_surrogate_key(['s.campus_id', 's.course_person_id']) }} as course_person_dim_key,
	{{ dbt_utils.generate_surrogate_key(['s.campus_id', 's.course_test_id']) }} as course_test_dim_key,
	{{ dbt_utils.generate_surrogate_key(['cp.campus_id', 'cp.course_id']) }} as course_dim_key,
	s.attempt_number,
	s.submission_text,
	s.score,
	s.submitted_time
from
	{{ source('els', 'submission') }} s
	INNER JOIN {{ source('els', 'course_person') }} cp
		ON cp.campus_id = s.campus_id
		AND cp.id = s.course_person_id
