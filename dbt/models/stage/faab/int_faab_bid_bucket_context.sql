{{
    config(
        materialized='table'
    )
}}

-- Per-league roster-gap and FA-scarcity flags for bid_bucket (#61).
-- Grain: league. Intermediate (stage schema) — not queried by Streamlit.
--
-- "My" team is the mart_weekly_lineup_inputs owner matching
-- owner_name_pattern (default ``%nolen%``). Cash leagues without a match
-- get gap_* = 0 so we never triage-from-gap there; scarcity still applies.
-- Athena has no QUALIFY — owner ties use row_number + filter.
--
-- Gap groups vs league_roster_slots (not weekly start/sit):
--   C vs 2, OF vs 5, 2B|SS vs 2B+SS+MI (3), 1B|3B vs 1B+3B+CI (3), P vs 9.
-- A player fills a gap when any pos token maps to a gapped group.
-- Scarce when unowned FA count for that group is < scarce_fa_count_max.

with thresholds as (
    select
        coalesce(max(cast(scarce_fa_count_max as double)), 3.0) as scarce_fa_count_max,
        coalesce(max(owner_name_pattern), '%nolen%') as owner_name_pattern
    from {{ ref('faab_bid_bucket_thresholds') }}
),

slot_needs as (
    select
        format,
        sum(case when slot = 'C' then "count" else 0 end) as need_c,
        sum(case when slot = 'OF' then "count" else 0 end) as need_of,
        sum(case when slot in ('2B', 'SS', 'MI') then "count" else 0 end) as need_mi,
        sum(case when slot in ('1B', '3B', 'CI') then "count" else 0 end) as need_ci,
        sum(case when slot = 'P' then "count" else 0 end) as need_p
    from {{ ref('league_roster_slots') }}
    group by 1
),

ranked_owners as (
    select
        matched_owners.league,
        matched_owners.owner,
        matched_owners.format,
        row_number() over (
            partition by matched_owners.league
            order by matched_owners.owner
        ) as rn
    from (
        select distinct
            li.league,
            li.owner,
            li.format
        from {{ ref('mart_weekly_lineup_inputs') }} li
        cross join thresholds t
        where li.owner is not null
          and trim(li.owner) <> ''
          and lower(li.owner) like lower(t.owner_name_pattern)
    ) matched_owners
),

my_owner as (
    select
        league,
        owner,
        format
    from ranked_owners
    where rn = 1
),

roster_counts as (
    select
        li.league,
        count(distinct case when li.is_c_eligible = 1 then li.nfbc_id end) as n_c,
        count(distinct case when li.is_of_eligible = 1 then li.nfbc_id end) as n_of,
        count(distinct case when li.is_mi_eligible = 1 then li.nfbc_id end) as n_mi,
        count(distinct case when li.is_ci_eligible = 1 then li.nfbc_id end) as n_ci,
        count(distinct case when li.is_p_eligible = 1 then li.nfbc_id end) as n_p
    from {{ ref('mart_weekly_lineup_inputs') }} li
    inner join my_owner mo
        on li.league = mo.league
        and li.owner = mo.owner
    group by 1
),

fa_counts as (
    select
        li.league,
        count(distinct case when li.is_c_eligible = 1 then li.nfbc_id end) as fa_c,
        count(distinct case when li.is_of_eligible = 1 then li.nfbc_id end) as fa_of,
        count(distinct case when li.is_mi_eligible = 1 then li.nfbc_id end) as fa_mi,
        count(distinct case when li.is_ci_eligible = 1 then li.nfbc_id end) as fa_ci,
        count(distinct case when li.is_p_eligible = 1 then li.nfbc_id end) as fa_p
    from {{ ref('mart_weekly_lineup_inputs') }} li
    where coalesce(trim(li.owner), '') = ''
    group by 1
)

select
    lc.league,
    mo.owner as my_owner,
    case
        when mo.owner is null then 0
        when coalesce(rc.n_c, 0) < coalesce(sn.need_c, 0) then 1
        else 0
    end as gap_c,
    case
        when mo.owner is null then 0
        when coalesce(rc.n_of, 0) < coalesce(sn.need_of, 0) then 1
        else 0
    end as gap_of,
    case
        when mo.owner is null then 0
        when coalesce(rc.n_mi, 0) < coalesce(sn.need_mi, 0) then 1
        else 0
    end as gap_mi,
    case
        when mo.owner is null then 0
        when coalesce(rc.n_ci, 0) < coalesce(sn.need_ci, 0) then 1
        else 0
    end as gap_ci,
    case
        when mo.owner is null then 0
        when coalesce(rc.n_p, 0) < coalesce(sn.need_p, 0) then 1
        else 0
    end as gap_p,
    case
        when coalesce(fc.fa_c, 0) < t.scarce_fa_count_max then 1
        else 0
    end as scarce_c,
    case
        when coalesce(fc.fa_of, 0) < t.scarce_fa_count_max then 1
        else 0
    end as scarce_of,
    case
        when coalesce(fc.fa_mi, 0) < t.scarce_fa_count_max then 1
        else 0
    end as scarce_mi,
    case
        when coalesce(fc.fa_ci, 0) < t.scarce_fa_count_max then 1
        else 0
    end as scarce_ci,
    case
        when coalesce(fc.fa_p, 0) < t.scarce_fa_count_max then 1
        else 0
    end as scarce_p
from {{ ref('league_config') }} lc
cross join thresholds t
left join my_owner mo
    on lc.league = mo.league
left join roster_counts rc
    on lc.league = rc.league
left join fa_counts fc
    on lc.league = fc.league
left join slot_needs sn
    on lc.format = sn.format
