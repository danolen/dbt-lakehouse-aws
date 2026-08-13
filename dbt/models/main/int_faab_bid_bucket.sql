{{
    config(
        materialized='view'
    )
}}

-- Classification harness for dbt unit tests (#61 / A6.3).
-- Production mart_faab_worksheet applies faab_bid_bucket() the same way.
-- This view is empty unless tests mock int_faab_bid_bucket_inputs.

with thresholds as (
    select
        coalesce(max(cast(cheap_high_bid_max as double)), 5.0) as cheap_high_bid_max,
        coalesce(max(cast(cheap_pct_of_faab_max as double)), 2.0) as cheap_pct_of_faab_max,
        coalesce(max(cast(expensive_high_bid_min as double)), 25.0) as expensive_high_bid_min,
        coalesce(max(cast(expensive_pct_of_faab_min as double)), 8.0) as expensive_pct_of_faab_min,
        coalesce(max(cast(borderline_high_bid_min as double)), 15.0) as borderline_high_bid_min,
        coalesce(max(cast(high_own_pct_min as double)), 90.0) as high_own_pct_min,
        coalesce(max(cast(ros_value_keeper_min as double)), 0.0) as ros_value_keeper_min
    from {{ ref('faab_bid_bucket_thresholds') }}
),

inputs as (
    select * from {{ ref('int_faab_bid_bucket_inputs') }}
)

select
    i.case_id,
    {{ faab_bid_bucket(
        'i.has_faab',
        'i.has_ftn_rec',
        'i.high_bid',
        'i.high_bid_pct_of_faab',
        'i.own_pct',
        'i.ros_value',
        'i.fills_roster_gap',
        'i.is_scarce_position',
        't.cheap_high_bid_max',
        't.cheap_pct_of_faab_max',
        't.expensive_high_bid_min',
        't.expensive_pct_of_faab_min',
        't.borderline_high_bid_min',
        't.high_own_pct_min',
        't.ros_value_keeper_min'
    ) }} as bid_bucket
from inputs i
cross join thresholds t
