{{
    config(
        materialized='table'
    )
}}

-- FAAB worksheet plus bid_bucket (#61 / pp. 200–201) and theoretical_bid
-- (#62 / p. 199). Both are observability only — never feed optimize_week
-- or FAAB what-if.

with league_config as (
    select
        league,
        -- ftn_league_size is null for draft-and-hold leagues (nolen_50).
        -- dbt-athena loads the seed column as integer, so empty CSV cells
        -- arrive as SQL NULL; the inner join to stg_ftn_faab below drops
        -- those rows naturally so no FAAB data gets attached.
        cast(ftn_league_size as int) as ftn_league_size,
        format
    from {{ ref('league_config') }}
),

my_faab as (
    -- Manually-maintained per-league budget remaining. Update weekly after
    -- waivers run in dbt/seeds/faab_remaining.csv, then re-seed. Competitor
    -- FAAB (opponents' remaining budgets) needs an NFBC scrape and lands
    -- in Phase 2b, not here.
    select
        league,
        cast(my_faab_remaining as int) as my_faab_remaining,
        cast(as_of_date as varchar) as faab_as_of_date
    from {{ ref('faab_remaining') }}
),

weekly as (
    select wp.*, lc.format, mf.my_faab_remaining, mf.faab_as_of_date
    from {{ ref('mart_weekly_projections') }} wp
    inner join league_config lc
        on wp.league = lc.league
    left join my_faab mf
        on wp.league = mf.league
),

ftn_by_league as (
    select
        ftn.nfbc_id,
        ftn.player_clean,
        ftn.position as ftn_position,
        ftn.team as ftn_team,
        ftn.type as ftn_type,
        ftn.low_bid,
        ftn.high_bid,
        ftn.notes_sp_matchups as ftn_notes,
        ftn.bid_change,
        ftn.status_tag,
        lc.league
    from {{ ref('stg_ftn_faab') }} ftn
    inner join league_config lc
        on ftn.league_size = lc.ftn_league_size
),

base as (
    select
        coalesce(wp.id, ftn.nfbc_id) as nfbc_id,
        coalesce(concat(wp.first_name, ' ', wp.last_name), ftn.player_clean) as player,
        coalesce(wp.pos, ftn.ftn_position) as position,
        coalesce(wp.team, ftn.ftn_team) as team,
        coalesce(wp.league, ftn.league) as league,
        wp.owner,
        cast(wp.own_pct as int) as own_pct,
        wp.week_of,
        wp.opps,
        wp.next_proj_opps,
        cast(wp.num_g as int) as num_g,
        wp.bats,
        cast(home_games as int) as home_games,
        cast(wp.away_games as int) as away_games,
        cast(vs_rhp as int) as vs_rhp,
        cast(wp.vs_lhp as int) as vs_lhp,
        cast(wp.dollars as double) as dollars,
        cast(wp.dollars_per_game as double) as dollars_per_game,
        cast(wp.dollars_monday_thursday as double) as dollars_monday_thursday,
        cast(wp.dollars_friday_sunday as double) as dollars_friday_sunday,
        cast(wp.roster_pct as int) as roster_pct,
        cast(wp.ros12_dollars_per_game as double) as ros12_dollars_per_game,
        cast(wp.rfs12 as int) as rfs12,
        cast(wp.rfs15 as int) as rfs15,
        cast(case wp.format
            when 'oc' then wp.ros_oc
            when 'me' then wp.ros_me
            when '50s' then wp.ros_50
        end as double) as ros_value,
        ftn.ftn_type,
        cast(nullif(ftn.low_bid, '') as int) as low_bid,
        cast(nullif(ftn.high_bid, '') as int) as high_bid,
        ftn.ftn_notes,
        ftn.bid_change,
        ftn.status_tag,
        cast(case when ftn.player_clean is not null then 1 else 0 end as int) as has_ftn_rec,
        wp.my_faab_remaining,
        wp.faab_as_of_date,
        -- What fraction of your remaining budget this bid would consume. Null
        -- for draft-and-hold (nolen_50 with my_faab_remaining=0) and for
        -- FTN-only rows with no matching weekly (where wp.* is all null).
        cast(
            case
                when wp.my_faab_remaining is null or wp.my_faab_remaining <= 0 then null
                else cast(nullif(ftn.high_bid, '') as double) / wp.my_faab_remaining * 100
            end as double
        ) as high_bid_pct_of_faab
    from weekly wp
    full outer join ftn_by_league ftn
        on wp.id = ftn.nfbc_id
        and wp.league = ftn.league
),

-- Bid-bucket cutoffs. Aggregate so a missing seed still yields one row of
-- defaults (a bare select from an empty seed would drop every worksheet row).
thresholds as (
    select
        coalesce(max(cast(cheap_high_bid_max as double)), 5.0) as cheap_high_bid_max,
        coalesce(max(cast(cheap_pct_of_faab_max as double)), 2.0) as cheap_pct_of_faab_max,
        coalesce(max(cast(expensive_high_bid_min as double)), 25.0) as expensive_high_bid_min,
        coalesce(max(cast(expensive_pct_of_faab_min as double)), 8.0) as expensive_pct_of_faab_min,
        coalesce(max(cast(borderline_high_bid_min as double)), 15.0) as borderline_high_bid_min,
        coalesce(max(cast(high_own_pct_min as double)), 90.0) as high_own_pct_min,
        coalesce(max(cast(ros_value_keeper_min as double)), 0.0) as ros_value_keeper_min
    from {{ ref('faab_bid_bucket_thresholds') }}
)

select
    b.*,
    -- Role bin from The Process pp. 200–201 (triage / tactical / strategic).
    -- FTN high_bid is market heat, not quality: expensive + ugly RoS stays
    -- strategic. Missing FTN is not a $0 bid (FTN skips ~90%+ owned names).
    -- Null when remaining FAAB is 0 (NFBC 50). Does not feed the optimizer
    -- or FAAB what-if scoring.
    {{ faab_bid_bucket(
        'case when b.my_faab_remaining is not null and b.my_faab_remaining > 0 then 1 else 0 end',
        'b.has_ftn_rec',
        'b.high_bid',
        'b.high_bid_pct_of_faab',
        'b.own_pct',
        'b.ros_value',
        faab_fills_roster_gap(
            faab_pos_array('b.position'),
            'c.gap_c',
            'c.gap_of',
            'c.gap_mi',
            'c.gap_ci',
            'c.gap_p'
        ),
        faab_is_scarce_position(
            faab_pos_array('b.position'),
            'c.scarce_c',
            'c.scarce_of',
            'c.scarce_mi',
            'c.scarce_ci',
            'c.scarce_p'
        ),
        't.cheap_high_bid_max',
        't.cheap_pct_of_faab_max',
        't.expensive_high_bid_min',
        't.expensive_pct_of_faab_min',
        't.borderline_high_bid_min',
        't.high_own_pct_min',
        't.ros_value_keeper_min'
    ) }} as bid_bucket,
    -- Share of remaining FAAB implied by positive RoS $ vs a per-format
    -- remaining-undrafted-value baseline (seed). Adapted from The Process
    -- p. 199 (book uses full-season waiver pool × league allowance).
    {{ faab_theoretical_bid(
        'b.ros_value',
        'b.my_faab_remaining',
        'tb.projected_remaining_undrafted_value'
    ) }} as theoretical_bid
from base b
left join {{ ref('int_faab_bid_bucket_context') }} c
    on b.league = c.league
left join league_config lc
    on b.league = lc.league
left join {{ ref('faab_theoretical_bid_baseline') }} tb
    on lc.format = tb.format
cross join thresholds t
