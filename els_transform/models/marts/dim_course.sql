select
	{{ dbt_utils.generate_surrogate_key(['c.campus_id', 'c.id']) }} as course_dim_key,
	c.campus_id,
	c.id AS course_id,
	sp.id AS study_program_id,
	t.id AS term_id,
	t.semester_type,
	t.academic_year,
	sp.name AS study_program_name,
	sp.code AS study_program_code,
	sp.description as study_program_description,
	tc.curriculum_type,
	c.course_number,
	c.course_type,
	c.name,
	c.description
from
	{{ source('els', 'course') }} AS c
	INNER JOIN  {{ source('els', 'term_course') }} tc
		ON tc.course_id = c.id
	INNER JOIN  {{ source('els', 'term') }} t
		ON t.id = tc.term_id
	INNER JOIN  {{ source('els', 'study_program') }} sp
		ON sp.id = t.study_program_id
