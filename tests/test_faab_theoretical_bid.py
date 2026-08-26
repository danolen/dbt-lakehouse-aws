"""Theoretical FAAB bid formula (#62 / The Process p. 199)."""

from faab_theoretical_bid import (
    THEORETICAL_BID_CAPTION,
    THEORETICAL_BID_HELP,
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


def test_tooltip_cites_process_page_199():
    assert "p. 199" in THEORETICAL_BID_HELP
    assert "The Process" in THEORETICAL_BID_HELP
    assert "p. 199" in THEORETICAL_BID_CAPTION
    assert "The Process" in THEORETICAL_BID_CAPTION
