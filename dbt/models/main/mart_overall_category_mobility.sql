{{
    config(
        materialized='table'
    )
}}

-- Overall-contest category mobility from actual cutlines (#183).
-- Primary signals: local marginal slope (±25 category points), nearest
-- distinct point islands, and raw-stat gaps to the 10/25/50/100 ladder.
-- Optional +1/+5 probes are included for density inspection only.

{% set slope_window = 25 %}
{% set ladder_deltas = [1, 5, 10, 25, 50, 100] %}

with base as (
    select *
    from {{ ref('stg_nfbc_overall_category_long') }}
),

point_levels as (
    select
        contest_key,
        snapshot_date,
        category,
        higher_is_better,
        category_points as point_level,
        min(raw_stat) as min_raw_at_level,
        max(raw_stat) as max_raw_at_level,
        count(*) as teams_at_level
    from base
    group by
        contest_key,
        snapshot_date,
        category,
        higher_is_better,
        category_points
),

-- raw_needed to reach at least this point_level (exact NFBC points island).
thresholds as (
    select
        contest_key,
        snapshot_date,
        category,
        higher_is_better,
        point_level as target_points,
        case
            when higher_is_better then
                min(min_raw_at_level) over (
                    partition by contest_key, snapshot_date, category
                    order by point_level
                    rows between current row and unbounded following
                )
            else
                max(max_raw_at_level) over (
                    partition by contest_key, snapshot_date, category
                    order by point_level
                    rows between current row and unbounded following
                )
        end as raw_needed
    from point_levels
),

nearest_above as (
    select
        b.contest_key,
        b.snapshot_date,
        b.team_key,
        b.category,
        min(p.point_level) as points_above
    from base b
    inner join point_levels p
        on b.contest_key = p.contest_key
        and b.snapshot_date = p.snapshot_date
        and b.category = p.category
        and p.point_level > b.category_points
    group by b.contest_key, b.snapshot_date, b.team_key, b.category
),

nearest_below as (
    select
        b.contest_key,
        b.snapshot_date,
        b.team_key,
        b.category,
        max(p.point_level) as points_below
    from base b
    inner join point_levels p
        on b.contest_key = p.contest_key
        and b.snapshot_date = p.snapshot_date
        and b.category = p.category
        and p.point_level < b.category_points
    group by b.contest_key, b.snapshot_date, b.team_key, b.category
),

ladder_targets as (
    select
        b.*,
        d.delta_points,
        b.category_points + d.delta_points as desired_points_up,
        b.category_points - d.delta_points as desired_points_down
    from base b
    cross join (
        {% for delta in ladder_deltas %}
        select {{ delta }} as delta_points
        {% if not loop.last %}union all{% endif %}
        {% endfor %}
    ) d
),

ladder_up as (
    select
        lt.contest_key,
        lt.snapshot_date,
        lt.team_key,
        lt.category,
        lt.delta_points,
        t.target_points as cutline_points,
        t.raw_needed as cutline_raw,
        row_number() over (
            partition by
                lt.contest_key,
                lt.snapshot_date,
                lt.team_key,
                lt.category,
                lt.delta_points
            order by t.target_points
        ) as rn
    from ladder_targets lt
    inner join thresholds t
        on lt.contest_key = t.contest_key
        and lt.snapshot_date = t.snapshot_date
        and lt.category = t.category
        and t.target_points >= lt.desired_points_up
),

ladder_down as (
    -- Downside: first point island at or below desired_points_down.
    -- raw_needed for that island is the threshold to *remain* at that
    -- level; falling below it means the next worse island.
    select
        lt.contest_key,
        lt.snapshot_date,
        lt.team_key,
        lt.category,
        lt.delta_points,
        t.target_points as cutline_points,
        t.raw_needed as cutline_raw,
        row_number() over (
            partition by
                lt.contest_key,
                lt.snapshot_date,
                lt.team_key,
                lt.category,
                lt.delta_points
            order by t.target_points desc
        ) as rn
    from ladder_targets lt
    inner join thresholds t
        on lt.contest_key = t.contest_key
        and lt.snapshot_date = t.snapshot_date
        and lt.category = t.category
        and t.target_points <= lt.desired_points_down
),

ladder_up_best as (
    select * from ladder_up where rn = 1
),

ladder_down_best as (
    select * from ladder_down where rn = 1
),

slope_up as (
    select
        b.contest_key,
        b.snapshot_date,
        b.team_key,
        b.category,
        t.target_points as slope_up_points,
        t.raw_needed as slope_up_raw,
        row_number() over (
            partition by b.contest_key, b.snapshot_date, b.team_key, b.category
            order by t.target_points
        ) as rn
    from base b
    inner join thresholds t
        on b.contest_key = t.contest_key
        and b.snapshot_date = t.snapshot_date
        and b.category = t.category
        and t.target_points >= b.category_points + {{ slope_window }}
),

slope_down as (
    select
        b.contest_key,
        b.snapshot_date,
        b.team_key,
        b.category,
        t.target_points as slope_down_points,
        t.raw_needed as slope_down_raw,
        row_number() over (
            partition by b.contest_key, b.snapshot_date, b.team_key, b.category
            order by t.target_points desc
        ) as rn
    from base b
    inner join thresholds t
        on b.contest_key = t.contest_key
        and b.snapshot_date = t.snapshot_date
        and b.category = t.category
        and t.target_points <= b.category_points - {{ slope_window }}
),

enriched as (
    select
        b.*,
        na.points_above,
        ta.raw_needed as raw_above,
        nb.points_below,
        tb.raw_needed as raw_below,
        su.slope_up_points,
        su.slope_up_raw,
        sd.slope_down_points,
        sd.slope_down_raw
        {% for delta in ladder_deltas %}
        ,
        lu{{ delta }}.cutline_points as cutline_points_up_{{ delta }},
        lu{{ delta }}.cutline_raw as cutline_raw_up_{{ delta }},
        ld{{ delta }}.cutline_points as cutline_points_down_{{ delta }},
        ld{{ delta }}.cutline_raw as cutline_raw_down_{{ delta }}
        {% endfor %}
    from base b
    left join nearest_above na
        on b.contest_key = na.contest_key
        and b.snapshot_date = na.snapshot_date
        and b.team_key = na.team_key
        and b.category = na.category
    left join thresholds ta
        on b.contest_key = ta.contest_key
        and b.snapshot_date = ta.snapshot_date
        and b.category = ta.category
        and na.points_above = ta.target_points
    left join nearest_below nb
        on b.contest_key = nb.contest_key
        and b.snapshot_date = nb.snapshot_date
        and b.team_key = nb.team_key
        and b.category = nb.category
    left join thresholds tb
        on b.contest_key = tb.contest_key
        and b.snapshot_date = tb.snapshot_date
        and b.category = tb.category
        and nb.points_below = tb.target_points
    left join slope_up su
        on b.contest_key = su.contest_key
        and b.snapshot_date = su.snapshot_date
        and b.team_key = su.team_key
        and b.category = su.category
        and su.rn = 1
    left join slope_down sd
        on b.contest_key = sd.contest_key
        and b.snapshot_date = sd.snapshot_date
        and b.team_key = sd.team_key
        and b.category = sd.category
        and sd.rn = 1
    {% for delta in ladder_deltas %}
    left join ladder_up_best lu{{ delta }}
        on b.contest_key = lu{{ delta }}.contest_key
        and b.snapshot_date = lu{{ delta }}.snapshot_date
        and b.team_key = lu{{ delta }}.team_key
        and b.category = lu{{ delta }}.category
        and lu{{ delta }}.delta_points = {{ delta }}
    left join ladder_down_best ld{{ delta }}
        on b.contest_key = ld{{ delta }}.contest_key
        and b.snapshot_date = ld{{ delta }}.snapshot_date
        and b.team_key = ld{{ delta }}.team_key
        and b.category = ld{{ delta }}.category
        and ld{{ delta }}.delta_points = {{ delta }}
    {% endfor %}
)

calc as (
    select
        enriched.*,
        case
            when raw_above is null then null
            when higher_is_better then raw_above - raw_stat
            else raw_stat - raw_above
        end as raw_gap_above,
        case
            when raw_below is null then null
            when higher_is_better then raw_stat - raw_below
            else raw_below - raw_stat
        end as raw_gap_below,
        case
            when slope_up_raw is null or slope_down_raw is null then null
            when higher_is_better then
                (slope_up_raw - slope_down_raw)
                / nullif(cast(slope_up_points - slope_down_points as double), 0)
            else
                (slope_down_raw - slope_up_raw)
                / nullif(cast(slope_up_points - slope_down_points as double), 0)
        end as raw_per_category_point
        {% for delta in ladder_deltas %}
        ,
        case
            when cutline_raw_up_{{ delta }} is null then null
            when higher_is_better then cutline_raw_up_{{ delta }} - raw_stat
            else raw_stat - cutline_raw_up_{{ delta }}
        end as raw_gap_up_{{ delta }},
        case
            when cutline_raw_down_{{ delta }} is null then null
            when higher_is_better then raw_stat - cutline_raw_down_{{ delta }}
            else cutline_raw_down_{{ delta }} - raw_stat
        end as raw_gap_down_{{ delta }}
        {% endfor %}
    from enriched
)

select
    contest_key,
    source_league_key,
    format,
    nfbc_overall_game_type_id,
    snapshot_date,
    is_latest_snapshot,
    team_key,
    owner,
    team,
    nfbc_league_id,
    overall_rank,
    overall_points,
    category,
    higher_is_better,
    is_ratio,
    raw_stat,
    category_points,
    category_rank,
    category_percentile,
    volume_ab,
    volume_h,
    volume_ip,
    volume_er,
    volume_bb_h,

    points_above,
    raw_above,
    raw_gap_above,
    points_below,
    raw_below,
    raw_gap_below,

    {{ slope_window }} as slope_window_points,
    slope_up_points,
    slope_up_raw,
    slope_down_points,
    slope_down_raw,
    raw_per_category_point,

    {% for delta in ladder_deltas %}
    cutline_points_up_{{ delta }},
    cutline_raw_up_{{ delta }},
    raw_gap_up_{{ delta }},
    cutline_points_down_{{ delta }},
    cutline_raw_down_{{ delta }},
    raw_gap_down_{{ delta }}{% if not loop.last %},{% endif %}
    {% endfor %}
    ,

    case
        when not is_ratio then raw_gap_above
        when category = 'AVG' and volume_ab is not null and raw_above is not null then
            (raw_above * volume_ab) - volume_h
        when category = 'ERA' and volume_ip is not null and volume_ip > 0 and raw_above is not null then
            volume_er - (raw_above * volume_ip / 9.0)
        when category = 'WHIP' and volume_ip is not null and volume_ip > 0 and raw_above is not null then
            volume_bb_h - (raw_above * volume_ip)
        else null
    end as count_equiv_gap_above,

    case
        when not is_ratio then raw_gap_up_10
        when category = 'AVG' and volume_ab is not null and cutline_raw_up_10 is not null then
            (cutline_raw_up_10 * volume_ab) - volume_h
        when category = 'ERA' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_10 is not null then
            volume_er - (cutline_raw_up_10 * volume_ip / 9.0)
        when category = 'WHIP' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_10 is not null then
            volume_bb_h - (cutline_raw_up_10 * volume_ip)
        else null
    end as count_equiv_up_10,

    case
        when not is_ratio then raw_gap_up_25
        when category = 'AVG' and volume_ab is not null and cutline_raw_up_25 is not null then
            (cutline_raw_up_25 * volume_ab) - volume_h
        when category = 'ERA' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_25 is not null then
            volume_er - (cutline_raw_up_25 * volume_ip / 9.0)
        when category = 'WHIP' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_25 is not null then
            volume_bb_h - (cutline_raw_up_25 * volume_ip)
        else null
    end as count_equiv_up_25,

    case
        when not is_ratio then raw_gap_up_50
        when category = 'AVG' and volume_ab is not null and cutline_raw_up_50 is not null then
            (cutline_raw_up_50 * volume_ab) - volume_h
        when category = 'ERA' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_50 is not null then
            volume_er - (cutline_raw_up_50 * volume_ip / 9.0)
        when category = 'WHIP' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_50 is not null then
            volume_bb_h - (cutline_raw_up_50 * volume_ip)
        else null
    end as count_equiv_up_50,

    case
        when not is_ratio then raw_gap_up_100
        when category = 'AVG' and volume_ab is not null and cutline_raw_up_100 is not null then
            (cutline_raw_up_100 * volume_ab) - volume_h
        when category = 'ERA' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_100 is not null then
            volume_er - (cutline_raw_up_100 * volume_ip / 9.0)
        when category = 'WHIP' and volume_ip is not null and volume_ip > 0 and cutline_raw_up_100 is not null then
            volume_bb_h - (cutline_raw_up_100 * volume_ip)
        else null
    end as count_equiv_up_100

from calc
