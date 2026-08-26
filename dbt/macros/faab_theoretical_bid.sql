{# Theoretical FAAB bid (#62 / The Process p. 199).

Book formula (printed p. 199):
  (Player X's Projected Positive Weekly Values
   / Total Positive Weekly Value to Enter League Via Waivers all Season)
   × Total League FAAB Allowance

Ticket #62 adapts two inputs:
  - remaining_budget is my_faab_remaining (A5.1 seed), not the full-season
    league allowance (typically $1,000 in NFBC).
  - projected_remaining_undrafted_value_for_season is a per-format
    hardcoded baseline (seed faab_theoretical_bid_baseline), not a live
    historical sum. Iterate later.

Numerator is format-specific Razzball ROS $ (ros_value). "Positive weekly
values" clamps negatives at 0. Null ROS (no weekly row) → null bid, not
$0 — unmatched FTN-only rows have no weekly context.

Observability only — never feed optimize_week or FAAB what-if.
#}

{% macro faab_theoretical_bid(ros_value, remaining_budget, remaining_undrafted_value) -%}
case
    when {{ remaining_budget }} is null or {{ remaining_budget }} <= 0
        then cast(null as int)
    when {{ remaining_undrafted_value }} is null or {{ remaining_undrafted_value }} <= 0
        then cast(null as int)
    when {{ ros_value }} is null
        then cast(null as int)
    else cast(
        round(
            (greatest({{ ros_value }}, 0) * 1.0 / {{ remaining_undrafted_value }})
            * {{ remaining_budget }}
        ) as int
    )
end
{%- endmacro %}
