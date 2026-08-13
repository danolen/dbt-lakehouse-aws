"""FAAB bid_bucket classification (#61)."""

from __future__ import annotations

from faab_bid_bucket import (
    classify_bid_bucket,
    fills_roster_gap,
    format_bid_bucket,
    gaps_from_counts,
    is_scarce_position,
    pos_tokens,
)


def test_gap_cheap_ftn_is_triage():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=3,
            high_bid_pct_of_faab=0.5,
            own_pct=5,
            ros_value=-4.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "triage"
    )


def test_expensive_ugly_ros_is_strategic():
    # FTN $ is heat, not quality — hyped prospect with ugly RoS stays 🏆.
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=80,
            high_bid_pct_of_faab=18.0,
            own_pct=2,
            ros_value=-12.0,
            fills_roster_gap=0,
            is_scarce_position=0,
        )
        == "strategic"
    )


def test_expensive_plus_gap_is_strategic_not_triage():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=80,
            high_bid_pct_of_faab=18.0,
            own_pct=8,
            ros_value=-3.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "strategic"
    )


def test_no_ftn_high_own_positive_ros_is_strategic():
    # Missing FTN is not a $0 bid; 90%+ own + RoS you'd want → contested FA.
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=0,
            high_bid=None,
            high_bid_pct_of_faab=None,
            own_pct=92,
            ros_value=4.5,
            fills_roster_gap=0,
            is_scarce_position=0,
        )
        == "strategic"
    )


def test_no_ftn_high_own_positive_ros_with_gap_still_strategic():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=0,
            high_bid=None,
            high_bid_pct_of_faab=None,
            own_pct=92,
            ros_value=4.5,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "strategic"
    )


def test_no_ftn_low_own_gap_is_triage():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=0,
            high_bid=None,
            high_bid_pct_of_faab=None,
            own_pct=12,
            ros_value=-1.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "triage"
    )


def test_no_faab_is_null():
    assert (
        classify_bid_bucket(
            has_faab=0,
            has_ftn_rec=1,
            high_bid=40,
            high_bid_pct_of_faab=None,
            own_pct=20,
            ros_value=2.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        is None
    )


def test_cheap_no_gap_is_tactical():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=3,
            high_bid_pct_of_faab=0.5,
            own_pct=8,
            ros_value=1.0,
            fills_roster_gap=0,
            is_scarce_position=0,
        )
        == "tactical"
    )


def test_no_ftn_high_own_neg_ros_no_gap_is_tactical():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=0,
            high_bid=None,
            high_bid_pct_of_faab=None,
            own_pct=92,
            ros_value=-6.0,
            fills_roster_gap=0,
            is_scarce_position=0,
        )
        == "tactical"
    )


def test_no_ftn_high_own_neg_ros_with_gap_is_triage():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=0,
            high_bid=None,
            high_bid_pct_of_faab=None,
            own_pct=92,
            ros_value=-6.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "triage"
    )


def test_borderline_scarce_is_strategic():
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=18,
            high_bid_pct_of_faab=4.0,
            own_pct=15,
            ros_value=0.5,
            fills_roster_gap=0,
            is_scarce_position=1,
        )
        == "strategic"
    )


def test_cheap_pct_of_faab_is_triage_even_if_bid_above_dollar_cutoff():
    # $8 on a large remaining budget can still be cheap via % of FAAB.
    assert (
        classify_bid_bucket(
            has_faab=1,
            has_ftn_rec=1,
            high_bid=8,
            high_bid_pct_of_faab=1.8,
            own_pct=10,
            ros_value=0.0,
            fills_roster_gap=1,
            is_scarce_position=0,
        )
        == "triage"
    )


def test_gaps_from_counts_and_no_owner():
    short_c = gaps_from_counts(n_c=1, n_of=6, n_mi=4, n_ci=4, n_p=10)
    assert short_c == {
        "gap_c": 1,
        "gap_of": 0,
        "gap_mi": 0,
        "gap_ci": 0,
        "gap_p": 0,
    }
    no_owner = gaps_from_counts(
        n_c=0, n_of=0, n_mi=0, n_ci=0, n_p=0, has_my_owner=False
    )
    assert no_owner == {
        "gap_c": 0,
        "gap_of": 0,
        "gap_mi": 0,
        "gap_ci": 0,
        "gap_p": 0,
    }


def test_player_fills_gapped_group_from_tokens():
    assert fills_roster_gap(pos_tokens("C,1B"), gap_c=1) == 1
    assert fills_roster_gap(pos_tokens("OF"), gap_c=1) == 0
    assert fills_roster_gap(pos_tokens("2B,SS"), gap_mi=1) == 1
    assert fills_roster_gap(pos_tokens("SP"), gap_p=1) == 1
    assert is_scarce_position(pos_tokens("C"), scarce_c=1) == 1
    assert is_scarce_position(pos_tokens("OF"), scarce_c=1) == 0


def test_format_bid_bucket_emojis():
    assert format_bid_bucket("triage") == "🩹 Triage"
    assert format_bid_bucket("tactical") == "🎯 Tactical"
    assert format_bid_bucket("strategic") == "🏆 Strategic"
    assert format_bid_bucket(None) == ""
    assert format_bid_bucket("") == ""
