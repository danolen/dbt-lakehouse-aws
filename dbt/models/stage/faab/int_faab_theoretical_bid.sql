{{
    config(
        materialized='view'
    )
}}

-- Formula harness for dbt unit tests (#62 / The Process p. 199).
-- Intermediate (stage schema) — not queried by Streamlit.
-- Production mart_faab_worksheet applies faab_theoretical_bid() the same way.
-- This view is empty unless tests mock int_faab_theoretical_bid_inputs.

select
    i.case_id,
    {{ faab_theoretical_bid(
        'i.ros_value',
        'i.my_faab_remaining',
        'i.projected_remaining_undrafted_value'
    ) }} as theoretical_bid
from {{ ref('int_faab_theoretical_bid_inputs') }} i
