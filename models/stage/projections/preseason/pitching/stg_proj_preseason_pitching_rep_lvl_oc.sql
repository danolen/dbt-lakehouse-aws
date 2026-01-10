{{
    config(
        materialized='table'
    )
}}

with base as (
    select *,
        case when row_number() over (order by sgp desc) <= 12*9 then 'Y'
            else 'N' end as include_in_pool
    from {{ ref('stg_proj_preseason_pitching_sgp_oc') }}
)

select position,
    min(sgp) as replvl
from base
where include_in_pool = 'Y'
group by 1