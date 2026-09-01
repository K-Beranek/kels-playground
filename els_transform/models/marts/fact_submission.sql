select
	s.id AS submission_id,
	s.campus_id,
	s.course_person_id,
	s.course_test_id,
	s.attempt_number,
	s.submission_text,
	s.score,
	s.submitted_time,
	cp.course_id
from
	{{ source('els', 'submission') }} s
	INNER JOIN {{ source('els', 'course_person') }} cp
		ON cp.id = s.course_person_id
