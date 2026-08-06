{{
    config(
        materialized='table',
        tags=['inseason']
    )
}}

-- Full NFBC in-season player snapshot history for #206. The latest-only
-- ``src_nfbc_in_season_players`` remains the consumer path for FAAB / lineup
-- marts so this ticket does not change projection joins.
select {{ dbt_utils.star(source('nfbc', 'in_season_players')) }},
    regexp_extract("$path", 'year=([0-9]{4})', 1) as year,
    regexp_extract("$path", 'month=([0-9]{1,2})', 1) as month,
    regexp_extract("$path", 'day=([0-9]{1,2})', 1) as day,
    concat(
        regexp_extract("$path", 'year=([0-9]{4})', 1),
        lpad(regexp_extract("$path", 'month=([0-9]{1,2})', 1), 2, '0'),
        lpad(regexp_extract("$path", 'day=([0-9]{1,2})', 1), 2, '0')
    ) as _ptkey,
    element_at(split("$path", '/'), -1) as _filename,
    current_timestamp as _loaddatetime
from {{ source('nfbc', 'in_season_players') }}
