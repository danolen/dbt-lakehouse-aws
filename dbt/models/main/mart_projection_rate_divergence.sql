{{
    config(
        materialized='table'
    )
}}

-- Observability only (#206): projected rate vs season-to-date rate.
-- Does NOT feed the optimizer, FAAB what-if scoring, or any projection math.
-- Thresholds live in seed ``projection_divergence_thresholds``.

with thresholds as (
    select
        upper(trim(stat)) as stat,
        lower(trim(projection_slice)) as projection_slice,
        cast(elevated_ratio as double) as elevated_ratio,
        cast(extreme_ratio as double) as extreme_ratio,
        cast(min_sample_volume as double) as min_sample_volume,
        lower(trim(volume_metric)) as volume_metric
    from {{ ref('projection_divergence_thresholds') }}
),

season as (
    select *
    from {{ ref('stg_nfbc_in_season_players_snapshots') }}
),

weekend_base as (
    select
        'weekend' as projection_slice,
        cast(null as varchar) as week_of,
        date(
            date_parse(
                concat(year, '-', lpad(month, 2, '0'), '-', lpad(day, 2, '0')),
                '%Y-%m-%d'
            )
        ) as projection_as_of,
        cast(nullif(trim(nfbcid), '') as varchar) as nfbc_id,
        nullif(trim(name), '') as player_name,
        cast(nullif(trim(ab), '') as double) as projected_volume,
        cast(nullif(trim(sb), '') as double) as proj_sb,
        cast(nullif(trim(hr), '') as double) as proj_hr,
        cast(nullif(trim(r), '') as double) as proj_r,
        cast(nullif(trim(rbi), '') as double) as proj_rbi
    from {{ ref('src_razzball_projections_weekend_hitting_history') }}
    where nullif(trim(nfbcid), '') is not null
),

weekly_base as (
    select
        'weekly' as projection_slice,
        nullif(trim(wk_of), '') as week_of,
        date(
            date_parse(
                concat(year, '-', lpad(month, 2, '0'), '-', lpad(day, 2, '0')),
                '%Y-%m-%d'
            )
        ) as projection_as_of,
        cast(nullif(trim(nfbcid), '') as varchar) as nfbc_id,
        nullif(trim(name), '') as player_name,
        cast(nullif(trim(ab), '') as double) as projected_volume,
        cast(nullif(trim(sb), '') as double) as proj_sb,
        cast(nullif(trim(hr), '') as double) as proj_hr,
        cast(nullif(trim(r), '') as double) as proj_r,
        cast(nullif(trim(rbi), '') as double) as proj_rbi
    from {{ ref('src_razzball_projections_weekly_hitting_history') }}
    where nullif(trim(nfbcid), '') is not null
),

mt_base as (
    select
        'monday_thursday' as projection_slice,
        cast(null as varchar) as week_of,
        date(
            date_parse(
                concat(year, '-', lpad(month, 2, '0'), '-', lpad(day, 2, '0')),
                '%Y-%m-%d'
            )
        ) as projection_as_of,
        cast(nullif(trim(nfbcid), '') as varchar) as nfbc_id,
        nullif(trim(name), '') as player_name,
        cast(nullif(trim(ab), '') as double) as projected_volume,
        cast(nullif(trim(sb), '') as double) as proj_sb,
        cast(nullif(trim(hr), '') as double) as proj_hr,
        cast(nullif(trim(r), '') as double) as proj_r,
        cast(nullif(trim(rbi), '') as double) as proj_rbi
    from {{ ref('src_razzball_projections_monday_thursday_hitting_history') }}
    where nullif(trim(nfbcid), '') is not null
),

hitter_long as (
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'SB' as stat, proj_sb as projected_value, projected_volume,
           cast(null as double) as projected_gs,
           cast(null as varchar) as projected_first_start_day,
           cast(null as varchar) as pitcher_opp
    from weekend_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'HR', proj_hr, projected_volume, null, null, null
    from weekend_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'R', proj_r, projected_volume, null, null, null
    from weekend_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'RBI', proj_rbi, projected_volume, null, null, null
    from weekend_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'SB', proj_sb, projected_volume, null, null, null
    from weekly_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'HR', proj_hr, projected_volume, null, null, null
    from weekly_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'R', proj_r, projected_volume, null, null, null
    from weekly_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'RBI', proj_rbi, projected_volume, null, null, null
    from weekly_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'SB', proj_sb, projected_volume, null, null, null
    from mt_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'HR', proj_hr, projected_volume, null, null, null
    from mt_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'R', proj_r, projected_volume, null, null, null
    from mt_base
    union all
    select projection_slice, week_of, projection_as_of, nfbc_id, player_name,
           'RBI', proj_rbi, projected_volume, null, null, null
    from mt_base
),

pitch_start as (
    select
        'weekly' as projection_slice,
        nullif(trim(week_of), '') as week_of,
        date(
            date_parse(
                concat(year, '-', lpad(month, 2, '0'), '-', lpad(day, 2, '0')),
                '%Y-%m-%d'
            )
        ) as projection_as_of,
        cast(nullif(trim(nfbcid), '') as varchar) as nfbc_id,
        nullif(trim(name), '') as player_name,
        'START' as stat,
        cast(null as double) as projected_value,
        cast(null as double) as projected_volume,
        cast(nullif(trim(gs), '') as double) as projected_gs,
        nullif(
            regexp_extract(coalesce(opp, ''), '\(([A-Z]{2})\)', 1),
            ''
        ) as projected_first_start_day,
        nullif(trim(opp), '') as pitcher_opp
    from {{ ref('src_razzball_projections_weekly_pitching_history') }}
    where nullif(trim(nfbcid), '') is not null
      and coalesce(cast(nullif(trim(gs), '') as double), 0) >= 1
),

projected as (
    select * from hitter_long
    union all
    select * from pitch_start
),

proj_keys as (
    select distinct nfbc_id, projection_as_of
    from projected
),

season_as_of as (
    select
        pk.nfbc_id as join_nfbc_id,
        pk.projection_as_of,
        s.players,
        s.ab,
        s.stolen_bases,
        s.home_runs,
        s.runs,
        s.rbi,
        s.ip_outs,
        s.snapshot_date
    from proj_keys pk
    left join season s
        on s.nfbc_id = pk.nfbc_id
        and s.snapshot_date <= pk.projection_as_of
    qualify row_number() over (
        partition by pk.nfbc_id, pk.projection_as_of
        order by s.snapshot_date desc nulls last
    ) = 1
),

season_week_later as (
    select
        pk.nfbc_id,
        pk.projection_as_of,
        s.ip_outs as ip_outs_later,
        s.snapshot_date as later_snapshot_date
    from (select distinct nfbc_id, projection_as_of from pitch_start) pk
    left join season s
        on s.nfbc_id = pk.nfbc_id
        and s.snapshot_date <= date_add('day', 7, pk.projection_as_of)
        and s.snapshot_date >= pk.projection_as_of
    qualify row_number() over (
        partition by pk.nfbc_id, pk.projection_as_of
        order by s.snapshot_date desc nulls last
    ) = 1
),

joined as (
    select
        pr.projection_slice,
        pr.week_of,
        pr.projection_as_of,
        pr.nfbc_id,
        coalesce(pr.player_name, sa.players) as player_name,
        pr.stat,
        pr.projected_value,
        pr.projected_volume,
        pr.projected_gs,
        pr.projected_first_start_day,
        pr.pitcher_opp,
        case pr.stat
            when 'SB' then sa.stolen_bases
            when 'HR' then sa.home_runs
            when 'R' then sa.runs
            when 'RBI' then sa.rbi
            else null
        end as season_value,
        case
            when pr.stat in ('SB', 'HR', 'R', 'RBI') then sa.ab
            else null
        end as season_volume,
        sa.snapshot_date as season_snapshot_date,
        sa.ip_outs as ip_outs_as_of,
        sl.ip_outs_later,
        sl.later_snapshot_date,
        t.elevated_ratio,
        t.extreme_ratio,
        t.min_sample_volume,
        t.volume_metric
    from projected pr
    left join season_as_of sa
        on sa.join_nfbc_id = pr.nfbc_id
        and sa.projection_as_of = pr.projection_as_of
    left join season_week_later sl
        on sl.nfbc_id = pr.nfbc_id
        and sl.projection_as_of = pr.projection_as_of
        and pr.stat = 'START'
    inner join thresholds t
        on t.stat = pr.stat
        and t.projection_slice = pr.projection_slice
),

scored as (
    select
        j.*,
        case
            when j.stat = 'START' then null
            when j.projected_volume is null or j.projected_volume <= 0 then null
            when j.projected_value is null then null
            else j.projected_value / j.projected_volume
        end as projected_rate,
        case
            when j.stat = 'START' then null
            when j.season_volume is null or j.season_volume <= 0 then null
            when j.season_value is null then null
            else j.season_value / j.season_volume
        end as season_rate,
        case
            when j.stat = 'START'
                and j.ip_outs_as_of is not null
                and j.ip_outs_later is not null
                and j.ip_outs_later > j.ip_outs_as_of
                then true
            when j.stat = 'START'
                and j.ip_outs_as_of is not null
                and j.ip_outs_later is not null
                then false
            else null
        end as start_occurred,
        cast(null as varchar) as realized_start_day
    from joined j
),

flagged as (
    select
        s.*,
        case
            when s.stat = 'START' then null
            when s.season_rate is null or s.season_rate <= 0 then null
            when s.projected_rate is null then null
            else s.projected_rate / s.season_rate
        end as divergence_ratio,
        case
            when s.stat = 'START' then true
            when s.season_volume is null then false
            when s.season_volume >= s.min_sample_volume then true
            else false
        end as min_sample_met
    from scored s
)

select
    projection_slice,
    week_of,
    projection_as_of,
    nfbc_id,
    player_name,
    stat,
    projected_value,
    projected_volume,
    projected_rate,
    season_value,
    season_volume,
    season_rate,
    season_snapshot_date,
    divergence_ratio,
    elevated_ratio,
    extreme_ratio,
    min_sample_volume,
    volume_metric,
    min_sample_met,
    case
        when stat = 'START' and start_occurred is null then 'unknown'
        when stat = 'START' and start_occurred then 'start_occurred'
        when stat = 'START' then 'start_missed'
        when not min_sample_met then 'insufficient_sample'
        when divergence_ratio is null then 'unknown'
        when divergence_ratio >= extreme_ratio then 'extreme'
        when divergence_ratio >= elevated_ratio then 'elevated'
        when divergence_ratio <= (1.0 / nullif(elevated_ratio, 0)) then 'depressed'
        else 'in_line'
    end as divergence_flag,
    projected_gs,
    projected_first_start_day,
    pitcher_opp,
    start_occurred,
    realized_start_day,
    later_snapshot_date,
    projection_as_of = max(projection_as_of) over (
        partition by projection_slice
    ) as is_latest_projection
from flagged
