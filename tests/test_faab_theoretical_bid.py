"""Theoretical FAAB bid formula (#62 / The Process p. 199)."""

from __future__ import annotations

import pandas as pd

from faab_theoretical_bid import (
    THEORETICAL_BID_CAPTION,
    THEORETICAL_BID_HELP,
    attach_theoretical_bid,
    theoretical_bid,
)


def test_positive_ros_rounds_to_whole_dollars():
    # 20 / 350 * 327 = 18.6857 → 19
    assert theoretical_bid(20.0, 327, 350.0) == 19


def test_zero_ros_is_zero():
    assert theoretical_bid(0.0, 327, 350.0) == 0


def test_negative_ros_clamps_to_zero():
    assert theoretical_bid(-5.0, 327, 350.0) == 0


def test_null_ros_is_null():
    assert theoretical_bid(None, 327, 350.0) is None


def test_no_remaining_budget_is_null():
    assert theoretical_bid(20.0, 0, 250.0) is None
    assert theoretical_bid(20.0, None, 350.0) is None
    assert theoretical_bid(20.0, -1, 350.0) is None


def test_zero_or_missing_baseline_is_null():
    assert theoretical_bid(20.0, 327, 0.0) is None
    assert theoretical_bid(20.0, 327, None) is None


def test_me_format_share():
    # 45 / 450 * 108 = 10.8 → 11
    assert theoretical_bid(45.0, 108, 450.0) == 11


def test_attach_uses_mart_column_when_present():
    df = pd.DataFrame(
        {
            "ros_value": [20.0],
            "my_faab_remaining": [327],
            "theoretical_bid": [99],
        }
    )
    out = attach_theoretical_bid(df, "oc")
    assert list(out["theoretical_bid"]) == [99]


def test_attach_computes_when_mart_column_missing():
    df = pd.DataFrame(
        {
            "ros_value": [20.0, -5.0, None],
            "my_faab_remaining": [327, 327, 327],
        }
    )
    out = attach_theoretical_bid(df, "oc")
    assert out["theoretical_bid"].iloc[0] == 19
    assert out["theoretical_bid"].iloc[1] == 0
    assert pd.isna(out["theoretical_bid"].iloc[2])


def test_attach_preserves_non_range_index():
    df = pd.DataFrame(
        {
            "ros_value": [20.0, -5.0],
            "my_faab_remaining": [327, 327],
        },
        index=[10, 20],
    )
    out = attach_theoretical_bid(df, "oc")
    assert out.loc[10, "theoretical_bid"] == 19
    assert out.loc[20, "theoretical_bid"] == 0


def test_tooltip_cites_process_page_199():
    assert "p. 199" in THEORETICAL_BID_HELP
    assert "The Process" in THEORETICAL_BID_HELP
    assert "p. 199" in THEORETICAL_BID_CAPTION
    assert "The Process" in THEORETICAL_BID_CAPTION


def test_attach_null_when_no_faab_or_unknown_format():
    df = pd.DataFrame({"ros_value": [20.0], "my_faab_remaining": [0]})
    out = attach_theoretical_bid(df, "oc")
    assert pd.isna(out["theoretical_bid"].iloc[0])
    out2 = attach_theoretical_bid(
        pd.DataFrame({"ros_value": [20.0], "my_faab_remaining": [327]}),
        "unknown",
    )
    assert pd.isna(out2["theoretical_bid"].iloc[0])
