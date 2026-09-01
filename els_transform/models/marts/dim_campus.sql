-- Use the `ref` function to select from other models

select
    {{ dbt_utils.generate_surrogate_key(['campus.campus_id']) }} as campus_dim_key,
    campus_id,
    uuid,
    code,
    name,
    description
from {{ ref('stg_els__campus') }} campus
