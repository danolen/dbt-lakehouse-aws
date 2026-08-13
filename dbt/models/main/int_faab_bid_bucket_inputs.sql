{{
    config(
        materialized='ephemeral'
    )
}}

-- Slim input grain for dbt unit tests of faab_bid_bucket (#61).
-- Empty in production; mart_faab_worksheet applies the same macro on live
-- worksheet rows. Unit tests mock this node (do not mock the wide FAAB join).

select
    cast(null as varchar) as case_id,
    cast(null as int) as has_faab,
    cast(null as int) as has_ftn_rec,
    cast(null as int) as high_bid,
    cast(null as double) as high_bid_pct_of_faab,
    cast(null as int) as own_pct,
    cast(null as double) as ros_value,
    cast(null as int) as fills_roster_gap,
    cast(null as int) as is_scarce_position
where 1 = 0
