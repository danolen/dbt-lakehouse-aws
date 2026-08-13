{# Bid-bucket helpers for mart_faab_worksheet (#61 / The Process pp. 200–201).

Triage / tactical / strategic are role bins (warm body vs weekly add vs
difference-maker), not FTN dollar tertiles. FTN high_bid is price / market
heat, not projected quality — a hyped call-up with ugly RoS stays strategic.

First matching CASE branch wins. Cutoffs live in seed
faab_bid_bucket_thresholds; do not hardcode them in the Streamlit app.
#}

{% macro faab_pos_array(position_expr) -%}
transform(
    split(upper(coalesce({{ position_expr }}, '')), ','),
    p -> trim(p)
)
{%- endmacro %}


{% macro faab_fills_roster_gap(pos_array_expr, gap_c, gap_of, gap_mi, gap_ci, gap_p) -%}
case
    when coalesce({{ gap_c }}, 0) = 1 and contains({{ pos_array_expr }}, 'C') then 1
    when coalesce({{ gap_of }}, 0) = 1 and contains({{ pos_array_expr }}, 'OF') then 1
    when coalesce({{ gap_mi }}, 0) = 1
        and (contains({{ pos_array_expr }}, '2B') or contains({{ pos_array_expr }}, 'SS'))
        then 1
    when coalesce({{ gap_ci }}, 0) = 1
        and (contains({{ pos_array_expr }}, '1B') or contains({{ pos_array_expr }}, '3B'))
        then 1
    when coalesce({{ gap_p }}, 0) = 1
        and (
            contains({{ pos_array_expr }}, 'P')
            or contains({{ pos_array_expr }}, 'SP')
            or contains({{ pos_array_expr }}, 'RP')
        )
        then 1
    else 0
end
{%- endmacro %}


{% macro faab_is_scarce_position(pos_array_expr, scarce_c, scarce_of, scarce_mi, scarce_ci, scarce_p) -%}
case
    when coalesce({{ scarce_c }}, 0) = 1 and contains({{ pos_array_expr }}, 'C') then 1
    when coalesce({{ scarce_of }}, 0) = 1 and contains({{ pos_array_expr }}, 'OF') then 1
    when coalesce({{ scarce_mi }}, 0) = 1
        and (contains({{ pos_array_expr }}, '2B') or contains({{ pos_array_expr }}, 'SS'))
        then 1
    when coalesce({{ scarce_ci }}, 0) = 1
        and (contains({{ pos_array_expr }}, '1B') or contains({{ pos_array_expr }}, '3B'))
        then 1
    when coalesce({{ scarce_p }}, 0) = 1
        and (
            contains({{ pos_array_expr }}, 'P')
            or contains({{ pos_array_expr }}, 'SP')
            or contains({{ pos_array_expr }}, 'RP')
        )
        then 1
    else 0
end
{%- endmacro %}


{% macro faab_bid_bucket(
    has_faab,
    has_ftn_rec,
    high_bid,
    high_bid_pct_of_faab,
    own_pct,
    ros_value,
    fills_roster_gap,
    is_scarce_position,
    cheap_high_bid_max,
    cheap_pct_of_faab_max,
    expensive_high_bid_min,
    expensive_pct_of_faab_min,
    borderline_high_bid_min,
    high_own_pct_min,
    ros_value_keeper_min
) -%}
case
    -- Draft-and-hold / no remaining budget (e.g. NFBC 50). Hide in the UI.
    when coalesce({{ has_faab }}, 0) = 0 then cast(null as varchar)

    -- Triage = cheap (or unlisted-and-not-contested) body that fills a hole.
    -- High FTN + gap is NOT triage — expensive market heat stays strategic.
    -- Missing FTN is not a $0 bid: FTN skips names owned in ~90%+ of leagues.
    when coalesce({{ fills_roster_gap }}, 0) = 1
        and (
            (
                coalesce({{ has_ftn_rec }}, 0) = 1
                and (
                    coalesce({{ high_bid }}, 0) <= {{ cheap_high_bid_max }}
                    or coalesce({{ high_bid_pct_of_faab }}, 0) <= {{ cheap_pct_of_faab_max }}
                )
            )
            or (
                coalesce({{ has_ftn_rec }}, 0) = 0
                and not (
                    coalesce({{ own_pct }}, 0) >= {{ high_own_pct_min }}
                    and coalesce({{ ros_value }}, -999) >= {{ ros_value_keeper_min }}
                )
            )
        )
        then 'triage'

    -- Strategic = expensive FTN heat, unpriced high-own keeper-quality FA,
    -- or a borderline FTN bid at a scarce position this week.
    when (
            coalesce({{ has_ftn_rec }}, 0) = 1
            and (
                coalesce({{ high_bid }}, 0) >= {{ expensive_high_bid_min }}
                or coalesce({{ high_bid_pct_of_faab }}, 0) >= {{ expensive_pct_of_faab_min }}
            )
        )
        or (
            coalesce({{ has_ftn_rec }}, 0) = 0
            and coalesce({{ own_pct }}, 0) >= {{ high_own_pct_min }}
            and coalesce({{ ros_value }}, -999) >= {{ ros_value_keeper_min }}
        )
        or (
            coalesce({{ has_ftn_rec }}, 0) = 1
            and coalesce({{ is_scarce_position }}, 0) = 1
            and coalesce({{ high_bid }}, 0) >= {{ borderline_high_bid_min }}
        )
        then 'strategic'

    else 'tactical'
end
{%- endmacro %}
