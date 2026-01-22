{{
    config(
        materialized='table'
    )
}}

select id,
    avg(pa) as pa
from {{ ref('stg_fg_proj_preseason_hitting_per_pa') }}
where proj_system in ('depthcharts','atc','thebat-x')
group by id

union all

select id,
    avg(pa) as pa
from {{ ref('stg_razzball_proj_preseason_hitting_per_pa') }}
where proj_system = 'razzball'
group by id