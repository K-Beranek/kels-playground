select
	{{ dbt_utils.generate_surrogate_key(['cp.campus_id', 'cp.id']) }} as course_person_dim_key,
	cp.id AS course_person_id,
	cp.campus_id,
	cp.course_id,
	cp.person_id,
	cp.course_role,
	p.uuid AS person_uuid,
	p.first_name,
	p.last_name
from
	{{ source('els', 'course_person') }} cp
	INNER JOIN {{ source('els', 'person') }} p
		ON p.id = cp.person_id
