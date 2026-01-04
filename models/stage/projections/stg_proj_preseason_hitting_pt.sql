{{
    config(
        materialized='table'
    )
}}

select id,
    avg(pa) as pa
from {{ ref('stg_fg_proj_preseason_hitting_per_pa') }}
where proj_system in ('depthcharts','steamer','thebat','thebat-x')
group by id