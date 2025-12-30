{{
    config(
        materialized='table'
    )
}}

select {{ dbt_utils.star(source('nfbc', 'standings')) }},
    concat(year,month,day) as _ptkey,
    element_at(SPLIT("$path", '/'), -1) as _filename
from {{ source('nfbc', 'standings') }}