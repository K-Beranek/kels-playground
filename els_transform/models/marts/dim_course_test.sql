select
	{{ dbt_utils.generate_surrogate_key(['ct.campus_id', 'ct.id']) }} as course_test_dim_key,
	ct.id as course_test_id,
	ct.campus_id,
	ct.code,
	ct.active,
	ct.test_questions,
	ct.possible_score,
	ct.required_score
from
	{{ source('els', 'course_test') }} ct
