select
    id as campus_id,
    uuid,
    code,
    name,
    description
from
    {{ source('els', 'campus') }}
