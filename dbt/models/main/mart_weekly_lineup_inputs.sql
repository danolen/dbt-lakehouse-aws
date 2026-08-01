{{
    config(
        materialized='table'
    )
}}

-- Weekly lineup input surface for expected-lineup optimization (#58).
-- One row per (league, owner, nfbc_id, row_type). Hitters and pitchers are
-- separate rows so two-way players (e.g. Ohtani) appear once in each role.
-- Free agents (empty owner) are included for add/drop what-if simulations.
--
-- Component counting stats and ratio numerators/denominators are exposed so
-- downstream code can aggregate H/AB, ER/IP, and (H+BB)/IP correctly.
-- Pitcher start metadata (first_start_day, is_two_start) is derived from the
-- Razzball weekly pitching file and is null-safe when no start is listed.

with league_formats as (
    select
        league,
        cast(ftn_league_size as int) as ftn_league_size,
        format
    from {{ ref('league_config') }}
),

base as (
    select
        wp.*,
        lf.format,
        lf.ftn_league_size,
        transform(
            split(upper(coalesce(wp.pos, '')), ','),
            p -> trim(p)
        ) as pos_array,
        cast(
            case lf.format
                when 'oc' then wp.ros_oc
                when 'me' then wp.ros_me
                when '50s' then wp.ros_50
            end as double
        ) as ros_value
    from {{ ref('mart_weekly_projections') }} wp
    inner join league_formats lf
        on wp.league = lf.league
),

hitters as (
    select
        b.league,
        b.format,
        b.ftn_league_size,
        b.owner,
        cast(b.own_pct as int) as own_pct,
        b.id as nfbc_id,
        trim(b.first_name) as first_name,
        trim(b.last_name) as last_name,
        concat(trim(b.first_name), ' ', trim(b.last_name)) as player_name,
        b.team,
        b.pos as pos_raw,
        b.pos_array,
        b.bats,
        b.week_of,
        'hitter' as row_type,

        cast(b.num_g as int) as num_g,
        cast(b.home_games as int) as home_games,
        cast(b.away_games as int) as away_games,
        cast(b.vs_rhp as int) as vs_rhp,
        cast(b.vs_lhp as int) as vs_lhp,
        cast(b.dollars as double) as dollars,
        cast(b.dollars_per_game as double) as dollars_per_game,
        cast(b.dollars_monday_thursday as double) as dollars_monday_thursday,
        cast(b.dollars_friday_sunday as double) as dollars_friday_sunday,
        b.ros_value,
        b.opps,

        -- Hitter component projections (full week)
        cast(b.hit_g as double) as hit_g,
        cast(b.pa as double) as pa,
        cast(b.ab as double) as ab,
        cast(b.hits as double) as hits,
        cast(b.r as double) as r,
        cast(b.hr as double) as hr,
        cast(b.rbi as double) as rbi,
        cast(b.sb as double) as sb,
        cast(b.bb as double) as bb,
        cast(b.so as double) as so,
        cast(b.batting_avg as double) as batting_avg,

        -- Mon–Thu components for Monday lock (#210)
        cast(b.has_monday_thursday_hitting as boolean) as has_monday_thursday_hitting,
        cast(b.mt_num_g as int) as mt_num_g,
        cast(b.mt_home_games as int) as mt_home_games,
        cast(b.mt_away_games as int) as mt_away_games,
        cast(b.mt_vs_rhp as int) as mt_vs_rhp,
        cast(b.mt_vs_lhp as int) as mt_vs_lhp,
        b.mt_opp,
        b.mt_sp,
        cast(b.mt_hit_g as double) as mt_hit_g,
        cast(b.mt_pa as double) as mt_pa,
        cast(b.mt_ab as double) as mt_ab,
        cast(b.mt_hits as double) as mt_hits,
        cast(b.mt_r as double) as mt_r,
        cast(b.mt_hr as double) as mt_hr,
        cast(b.mt_rbi as double) as mt_rbi,
        cast(b.mt_sb as double) as mt_sb,
        cast(b.mt_bb as double) as mt_bb,
        cast(b.mt_so as double) as mt_so,
        cast(b.mt_batting_avg as double) as mt_batting_avg,

        -- Pitcher fields null on hitter rows
        cast(null as varchar) as pitcher_pos,
        cast(null as varchar) as pitcher_opp,
        cast(null as double) as pitch_g,
        cast(null as double) as gs,
        cast(null as double) as projected_starts,
        cast(null as varchar) as first_start_day,
        cast(null as boolean) as is_two_start,
        cast(null as double) as qs,
        cast(null as double) as w,
        cast(null as double) as l,
        cast(null as double) as sv,
        cast(null as double) as hld,
        cast(null as double) as ip,
        cast(null as double) as hits_allowed,
        cast(null as double) as er,
        cast(null as double) as k,
        cast(null as double) as walks_allowed,
        cast(null as double) as hr_allowed,
        cast(null as double) as era,
        cast(null as double) as whip,
        cast(null as varchar) as next_proj_opps,

        cast(contains(b.pos_array, 'C') as int) as is_c_eligible,
        cast(contains(b.pos_array, '1B') as int) as is_1b_eligible,
        cast(contains(b.pos_array, '2B') as int) as is_2b_eligible,
        cast(contains(b.pos_array, '3B') as int) as is_3b_eligible,
        cast(contains(b.pos_array, 'SS') as int) as is_ss_eligible,
        cast(contains(b.pos_array, 'OF') as int) as is_of_eligible,
        cast(
            (contains(b.pos_array, '2B') or contains(b.pos_array, 'SS')) as int
        ) as is_mi_eligible,
        cast(
            (contains(b.pos_array, '1B') or contains(b.pos_array, '3B')) as int
        ) as is_ci_eligible,
        1 as is_util_eligible,
        0 as is_p_eligible
    from base b
    where b.has_weekly_hitting
),

pitchers as (
    select
        b.league,
        b.format,
        b.ftn_league_size,
        b.owner,
        cast(b.own_pct as int) as own_pct,
        b.id as nfbc_id,
        trim(b.first_name) as first_name,
        trim(b.last_name) as last_name,
        concat(trim(b.first_name), ' ', trim(b.last_name)) as player_name,
        b.team,
        -- Prefer Razzball SP/RP label; fall back to NFBC pos string.
        coalesce(b.pitcher_pos, b.pos) as pos_raw,
        transform(
            split(upper(coalesce(coalesce(b.pitcher_pos, b.pos), '')), ','),
            p -> trim(p)
        ) as pos_array,
        cast(null as varchar) as bats,
        b.week_of,
        'pitcher' as row_type,

        cast(null as int) as num_g,
        cast(null as int) as home_games,
        cast(null as int) as away_games,
        cast(null as int) as vs_rhp,
        cast(null as int) as vs_lhp,
        cast(b.dollars as double) as dollars,
        cast(b.dollars_per_game as double) as dollars_per_game,
        cast(null as double) as dollars_monday_thursday,
        cast(null as double) as dollars_friday_sunday,
        b.ros_value,
        coalesce(b.pitcher_opp, b.opps) as opps,

        cast(null as double) as hit_g,
        cast(null as double) as pa,
        cast(null as double) as ab,
        cast(null as double) as hits,
        cast(null as double) as r,
        cast(null as double) as hr,
        cast(null as double) as rbi,
        cast(null as double) as sb,
        cast(null as double) as bb,
        cast(null as double) as so,
        cast(null as double) as batting_avg,

        cast(null as boolean) as has_monday_thursday_hitting,
        cast(null as int) as mt_num_g,
        cast(null as int) as mt_home_games,
        cast(null as int) as mt_away_games,
        cast(null as int) as mt_vs_rhp,
        cast(null as int) as mt_vs_lhp,
        cast(null as varchar) as mt_opp,
        cast(null as varchar) as mt_sp,
        cast(null as double) as mt_hit_g,
        cast(null as double) as mt_pa,
        cast(null as double) as mt_ab,
        cast(null as double) as mt_hits,
        cast(null as double) as mt_r,
        cast(null as double) as mt_hr,
        cast(null as double) as mt_rbi,
        cast(null as double) as mt_sb,
        cast(null as double) as mt_bb,
        cast(null as double) as mt_so,
        cast(null as double) as mt_batting_avg,

        b.pitcher_pos,
        b.pitcher_opp,
        cast(b.pitch_g as double) as pitch_g,
        cast(b.gs as double) as gs,
        cast(b.gs as double) as projected_starts,
        -- First parenthetical day code in Opp, e.g. "@NYM(TU) / WSH(SU)" -> TU.
        -- Null-safe when Opp is blank or has no day codes (RP / no start listed).
        nullif(
            regexp_extract(coalesce(b.pitcher_opp, ''), '\(([A-Z]{2})\)', 1),
            ''
        ) as first_start_day,
        case
            when b.gs is not null and b.gs >= 2 then true
            when cardinality(
                regexp_extract_all(coalesce(b.pitcher_opp, ''), '\(([A-Z]{2})\)')
            ) >= 2 then true
            when b.gs is not null and b.gs < 2 then false
            when coalesce(b.pitcher_opp, '') = '' then false
            else false
        end as is_two_start,
        cast(b.qs as double) as qs,
        cast(b.w as double) as w,
        cast(b.l as double) as l,
        cast(b.sv as double) as sv,
        cast(b.hld as double) as hld,
        cast(b.ip as double) as ip,
        cast(b.hits_allowed as double) as hits_allowed,
        cast(b.er as double) as er,
        cast(b.k as double) as k,
        cast(b.walks_allowed as double) as walks_allowed,
        cast(b.hr_allowed as double) as hr_allowed,
        cast(b.era as double) as era,
        cast(b.whip as double) as whip,
        b.next_proj_opps,

        0 as is_c_eligible,
        0 as is_1b_eligible,
        0 as is_2b_eligible,
        0 as is_3b_eligible,
        0 as is_ss_eligible,
        0 as is_of_eligible,
        0 as is_mi_eligible,
        0 as is_ci_eligible,
        0 as is_util_eligible,
        1 as is_p_eligible
    from base b
    where b.has_weekly_pitching
)

select * from hitters
union all
select * from pitchers
