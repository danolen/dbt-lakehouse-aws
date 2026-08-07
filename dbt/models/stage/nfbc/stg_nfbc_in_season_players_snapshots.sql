{{
    config(
        materialized='table'
    )
}}

-- Typed cumulative NFBC roster stats by snapshot date (#206).
-- Dedupes the five league CSVs per day (same nfbc id / cumulative line).
with cleaned as (
    select
        cast(nullif(trim(id), '') as varchar) as nfbc_id,
        nullif(trim(players), '') as players,
        {{ nfbc_parse_number('at_bats', 'double') }} as ab,
        {{ nfbc_parse_number('hits', 'double') }} as hits,
        {{ nfbc_parse_number('runs', 'double') }} as runs,
        {{ nfbc_parse_number('home_runs', 'double') }} as home_runs,
        {{ nfbc_parse_number('runs_batted_in', 'double') }} as rbi,
        {{ nfbc_parse_number('stolen_bases', 'double') }} as stolen_bases,
        {{ nfbc_parse_number('innings_pitched', 'double') }} as ip_raw,
        {{ nfbc_parse_number('strikeouts', 'double') }} as strikeouts,
        {{ nfbc_parse_number('wins', 'double') }} as wins,
        {{ nfbc_parse_number('saves', 'double') }} as saves,
        date(
            date_parse(
                concat(year, '-', lpad(month, 2, '0'), '-', lpad(day, 2, '0')),
                '%Y-%m-%d'
            )
        ) as snapshot_date,
        year,
        month,
        day,
        _ptkey,
        _filename,
        _loaddatetime
    from {{ ref('src_nfbc_in_season_players_history') }}
    where nullif(trim(id), '') is not null
),

with_outs as (
    select
        cleaned.*,
        case
            when ip_raw is null then null
            else {{ baseball_ip_to_outs('ip_raw') }}
        end as ip_outs
    from cleaned
),

deduped as (
    select
        *,
        row_number() over (
            partition by nfbc_id, snapshot_date
            order by _filename
        ) as _rn
    from with_outs
)

select
    nfbc_id,
    players,
    ab,
    hits,
    runs,
    home_runs,
    rbi,
    stolen_bases,
    ip_raw,
    ip_outs,
    strikeouts,
    wins,
    saves,
    snapshot_date,
    snapshot_date = max(snapshot_date) over () as is_latest_snapshot,
    year,
    month,
    day,
    _ptkey,
    _filename,
    _loaddatetime
from deduped
where _rn = 1
