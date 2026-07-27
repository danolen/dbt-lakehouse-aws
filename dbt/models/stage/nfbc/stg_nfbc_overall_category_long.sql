{{
    config(
        materialized='table'
    )
}}

-- One row per contest/snapshot/team/category for overall standings.
-- Joins typed category stats + points and unpivots the ten scoring
-- categories. Volume numerators/denominators are carried for ratio
-- equivalents in the mobility mart (#183).

with joined as (
    select
        stats.source_league_key,
        stats.snapshot_date,
        stats.is_latest_snapshot,
        stats.format,
        stats.nfbc_overall_game_type_id,
        stats.standing_rank,
        stats.owner,
        stats.team,
        stats.nfbc_league_id,
        stats.overall_points,
        stats.r,
        stats.hr,
        stats.rbi,
        stats.sb,
        stats.ab,
        stats.h,
        stats.avg,
        stats.k,
        stats.w,
        stats.sv,
        stats.ip,
        stats.er,
        stats.era,
        stats.bb,
        stats.ha,
        stats.whip,
        pts.r_pts,
        pts.hr_pts,
        pts.rbi_pts,
        pts.sb_pts,
        pts.avg_pts,
        pts.k_pts,
        pts.w_pts,
        pts.sv_pts,
        pts.era_pts,
        pts.whip_pts
    from {{ ref('stg_nfbc_in_season_overall_category_stats') }} stats
    inner join {{ ref('stg_nfbc_in_season_overall_category_points') }} pts
        on stats.source_league_key = pts.source_league_key
        and stats.snapshot_date = pts.snapshot_date
        and stats.owner = pts.owner
        and stats.team = pts.team
        and stats.nfbc_league_id = pts.nfbc_league_id
),

unpivoted as (
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'R' as category, cast(r as double) as raw_stat, r_pts as category_points,
           true as higher_is_better, false as is_ratio
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'HR', cast(hr as double), hr_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'RBI', cast(rbi as double), rbi_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'SB', cast(sb as double), sb_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'AVG', avg, avg_pts, true, true
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'K', cast(k as double), k_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'W', cast(w as double), w_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'SV', cast(sv as double), sv_pts, true, false
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'ERA', era, era_pts, false, true
    from joined
    union all
    select source_league_key, snapshot_date, is_latest_snapshot, format,
           nfbc_overall_game_type_id, standing_rank, owner, team,
           nfbc_league_id, overall_points, ab, h, ip, er, bb, ha,
           'WHIP', whip, whip_pts, false, true
    from joined
)

select
    source_league_key as contest_key,
    source_league_key,
    format,
    nfbc_overall_game_type_id,
    snapshot_date,
    is_latest_snapshot,
    concat(
        source_league_key,
        '|',
        cast(nfbc_league_id as varchar),
        '|',
        team
    ) as team_key,
    owner,
    team,
    nfbc_league_id,
    standing_rank as overall_rank,
    overall_points,
    category,
    raw_stat,
    category_points,
    higher_is_better,
    is_ratio,
    cast(ab as double) as volume_ab,
    cast(h as double) as volume_h,
    cast(ip as double) as volume_ip,
    cast(er as double) as volume_er,
    cast(bb as double) + cast(ha as double) as volume_bb_h,
    dense_rank() over (
        partition by source_league_key, snapshot_date, category
        order by category_points desc, standing_rank
    ) as category_rank,
    percent_rank() over (
        partition by source_league_key, snapshot_date, category
        order by category_points
    ) as category_percentile
from unpivoted
where raw_stat is not null
  and category_points is not null
