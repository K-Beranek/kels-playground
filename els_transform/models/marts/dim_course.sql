select
	c.id AS course_id,
	c.campus_id,
	sp.id AS study_program_id,
	s.id AS semester_id,
	t.id AS term_id,
	s.semester_type,
	s.academic_year,
	s.code AS semester_code,
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
	INNER JOIN  {{ source('els', 'semester') }} s
		ON s.id = t.semester_id
