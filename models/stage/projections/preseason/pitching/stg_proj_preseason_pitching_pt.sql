{{
    config(
        materialized='table'
    )
}}

select id,
    avg(ip) as ip
from {{ ref('stg_fg_proj_preseason_pitching_per_ip') }}
where proj_system in ('depthcharts','atc','thebat')
group by id

union all

select id,
    avg(ip) as ip
from {{ ref('stg_razzball_proj_preseason_pitching_per_ip') }}
where proj_system = 'razzball'
group by id