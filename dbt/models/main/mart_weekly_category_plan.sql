{{
    config(
        materialized='table'
    )
}}

-- Weekly category targets for overall contests (#186).
-- Grain: one row per (league, team_key, category) on the latest mobility
-- snapshot. Expected-lineup projection and gap classification happen in the
-- app (Hungarian assignment is not expressible here).
--
-- Maintain = current season pace (raw / weeks_elapsed).
-- Stretch = maintain + (raw_gap_up_N / weeks_remaining) for counting stats;
--           cutline rate for ratio categories (AVG/ERA/WHIP).
-- Non-overall leagues are excluded (nfbc_overall_game_type_id is null).

with calendar as (
    select
        cast(season_year as int) as season_year,
        cast(scoring_periods as int) as season_scoring_periods,
        cast(season_start_date as date) as season_start_date
    from {{ ref('season_scoring_calendar') }}
),

overall_leagues as (
    select
        league,
        format,
        cast(nfbc_overall_game_type_id as int) as nfbc_overall_game_type_id,
        cast(nfbc_league_id as int) as nfbc_league_id
    from {{ ref('league_config') }}
    where nfbc_overall_game_type_id is not null
),

week_label as (
    select max(week_of) as week_of
    from {{ ref('mart_weekly_lineup_inputs') }}
),

mobility as (
    select m.*
    from {{ ref('mart_overall_category_mobility') }} m
    inner join overall_leagues ol
        on m.contest_key = ol.league
    where m.is_latest_snapshot
),

paced as (
    select
        m.contest_key as league,
        m.format,
        m.nfbc_overall_game_type_id,
        m.snapshot_date,
        w.week_of,
        m.team_key,
        m.owner as standings_owner,
        m.team as team_name,
        m.nfbc_league_id,
        m.overall_rank,
        m.overall_points,
        m.category,
        m.higher_is_better,
        m.is_ratio,
        m.raw_stat as current_raw,
        m.category_points as current_category_points,
        m.volume_ab,
        m.volume_h,
        m.volume_ip,
        m.volume_er,
        m.volume_bb_h,
        m.headroom_status,
        m.raw_unit_size,
        m.overall_points_per_raw_unit,
        m.teams_at_current_points,
        m.tie_cluster_raw_width,
        -- Noise floor: at least one decision unit; widen to the current
        -- point-island raw span when teams are clustered on a range.
        greatest(
            coalesce(m.tie_cluster_raw_width, 0.0),
            coalesce(m.raw_unit_size, 1.0)
        ) as noise_floor_raw,
        m.raw_gap_up_25,
        m.raw_gap_up_50,
        m.raw_gap_up_100,
        m.ladder_up_status_25,
        m.ladder_up_status_50,
        m.ladder_up_status_100,
        m.cutline_raw_up_25,
        m.cutline_raw_up_50,
        m.cutline_raw_up_100,
        m.count_equiv_up_25,
        m.count_equiv_up_50,
        m.count_equiv_up_100,
        c.season_scoring_periods,
        c.season_start_date,
        greatest(
            1,
            date_diff('week', c.season_start_date, m.snapshot_date) + 1
        ) as weeks_elapsed,
        greatest(
            1,
            c.season_scoring_periods
            - greatest(1, date_diff('week', c.season_start_date, m.snapshot_date) + 1)
        ) as weeks_remaining
    from mobility m
    cross join calendar c
    cross join week_label w
    where c.season_year = year(m.snapshot_date)
)

select
    league,
    format,
    nfbc_overall_game_type_id,
    snapshot_date,
    week_of,
    team_key,
    standings_owner,
    team_name,
    nfbc_league_id,
    overall_rank,
    overall_points,
    category,
    higher_is_better,
    is_ratio,
    current_raw,
    current_category_points,
    volume_ab,
    volume_h,
    volume_ip,
    volume_er,
    volume_bb_h,
    season_scoring_periods,
    season_start_date,
    weeks_elapsed,
    weeks_remaining,
    headroom_status,
    raw_unit_size,
    overall_points_per_raw_unit,
    teams_at_current_points,
    tie_cluster_raw_width,
    noise_floor_raw,
    raw_gap_up_25,
    raw_gap_up_50,
    raw_gap_up_100,
    ladder_up_status_25,
    ladder_up_status_50,
    ladder_up_status_100,
    count_equiv_up_25,
    count_equiv_up_50,
    count_equiv_up_100,

    -- Maintain weekly target (counting = pace; ratio = current rate).
    case
        when is_ratio then current_raw
        else current_raw / cast(weeks_elapsed as double)
    end as maintain_weekly_target,

    -- Stretch weekly targets for +25 / +50 / +100 overall category points.
    case
        when is_ratio then cutline_raw_up_25
        when raw_gap_up_25 is null then null
        else (current_raw / cast(weeks_elapsed as double))
            + (raw_gap_up_25 / cast(weeks_remaining as double))
    end as stretch_weekly_target_25,
    case
        when is_ratio then cutline_raw_up_50
        when raw_gap_up_50 is null then null
        else (current_raw / cast(weeks_elapsed as double))
            + (raw_gap_up_50 / cast(weeks_remaining as double))
    end as stretch_weekly_target_50,
    case
        when is_ratio then cutline_raw_up_100
        when raw_gap_up_100 is null then null
        else (current_raw / cast(weeks_elapsed as double))
            + (raw_gap_up_100 / cast(weeks_remaining as double))
    end as stretch_weekly_target_100,

    -- Ratio helpers: hits / ER / H+BB needed this week at a given projected volume
    -- are computed in the app once expected lineup AB/IP are known.
    case
        when category = 'AVG' then 'hits_at_projected_ab'
        when category = 'ERA' then 'er_at_projected_ip'
        when category = 'WHIP' then 'bb_h_at_projected_ip'
        else 'raw_stat'
    end as target_unit
from paced
