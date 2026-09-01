select
    campus_id,
    id as course_id,
    course_type,
    name,
    course_number,
    description
from
    {{ source('els', 'course') }}
