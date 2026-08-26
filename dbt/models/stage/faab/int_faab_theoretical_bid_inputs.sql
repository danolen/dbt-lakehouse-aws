{{
    config(
        materialized='ephemeral'
    )
}}

-- Slim input grain for dbt unit tests of faab_theoretical_bid (#62).
-- Intermediate (ephemeral; stage folder). Empty in production;
-- mart_faab_worksheet applies the same macro on live worksheet rows.
-- Unit tests mock this node (do not mock the wide FAAB join).

select
    cast(null as varchar) as case_id,
    cast(null as double) as ros_value,
    cast(null as int) as my_faab_remaining,
    cast(null as double) as projected_remaining_undrafted_value
where 1 = 0
