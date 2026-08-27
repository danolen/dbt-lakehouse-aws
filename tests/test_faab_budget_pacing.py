"""FAAB budget pacing vs 2025 Appendix p. 76 (#64)."""

from datetime import date

from faab_budget_pacing import (
    APPENDIX_LAST_WEEK,
    APPENDIX_PAGE,
    DEFAULT_STARTING_BUDGET,
    PACING_CAPTION,
    STATUS_HOARDING,
    STATUS_ON_PACE,
    STATUS_OVERSPENDING,
    classify_pace,
    curve_spend_at,
    load_pacing_curves,
    marker_week,
    pacing_snapshot,
    parse_week_date,
    season_week_number,
    spent_to_date,
)


def test_spent_to_date_from_remaining():
    assert spent_to_date(327) == 673
    assert spent_to_date(0) == 1000
    assert spent_to_date(None) is None


def test_appendix_curves_match_page_76():
    curves = load_pacing_curves()
    assert curve_spend_at(curves, 2, "elite_cumulative_spend") == 88
    assert curve_spend_at(curves, 2, "first_quartile_cumulative_spend") == 61
    assert curve_spend_at(curves, 7, "elite_cumulative_spend") == 382
    assert curve_spend_at(curves, 20, "elite_cumulative_spend") == 898
    assert curve_spend_at(curves, 20, "first_quartile_cumulative_spend") == 875
    # Hold last sample week — do not invent weeks 21–26.
    assert curve_spend_at(curves, 26, "elite_cumulative_spend") == 898


def test_overspending_when_remaining_below_elite():
    # Week 7 Elite remaining = 1000-382 = 618.
    snap = pacing_snapshot(remaining=327, weeks_remaining=19, week=7)
    assert snap is not None
    assert snap.spent_to_date == 673
    assert snap.status == STATUS_OVERSPENDING
    assert snap.my_weekly_capacity == 327 / 19


def test_hoarding_when_remaining_above_q1():
    # Week 20 1st remaining = 1000-875 = 125.
    snap = pacing_snapshot(remaining=327, weeks_remaining=4, week=22)
    assert snap is not None
    assert snap.sample_ended is True
    assert snap.week == 22
    assert snap.status == STATUS_HOARDING


def test_on_pace_inside_elite_q1_band():
    # Week 20 elite rem 102, q1 rem 125.
    snap = pacing_snapshot(remaining=110, weeks_remaining=4, week=20)
    assert snap is not None
    assert snap.status == STATUS_ON_PACE
    assert snap.sample_ended is False


def test_no_snapshot_without_remaining_faab():
    assert pacing_snapshot(remaining=0, weeks_remaining=4, week=10) is None
    assert pacing_snapshot(remaining=None, weeks_remaining=4, week=10) is None


def test_snapshot_is_a_single_marker_not_a_series():
    snap = pacing_snapshot(remaining=140, weeks_remaining=4, week=20)
    assert snap is not None
    assert not hasattr(snap, "weekly_spend")
    assert isinstance(snap.spent_to_date, int)


def test_classify_pace_bounds():
    assert classify_pace(50, elite_remaining=102, q1_remaining=125) == STATUS_OVERSPENDING
    assert classify_pace(110, elite_remaining=102, q1_remaining=125) == STATUS_ON_PACE
    assert classify_pace(200, elite_remaining=102, q1_remaining=125) == STATUS_HOARDING


def test_marker_week_prefers_as_of_over_week_of():
    # Remaining seed as_of 2026-05-10; worksheet week_of 8/24.
    week = marker_week(as_of_value="2026-05-10", week_of_value="8/24")
    assert week == season_week_number(date(2026, 5, 10))
    assert week < season_week_number(date(2026, 8, 24))


def test_parse_razzball_week_of():
    assert parse_week_date("8/24") == date(2026, 8, 24)


def test_caption_cites_appendix_page_76():
    assert "p. 76" in PACING_CAPTION
    assert APPENDIX_PAGE == "2025 Appendix p. 76"
    assert str(APPENDIX_LAST_WEEK) in PACING_CAPTION
    assert "not a weekly spend history" in PACING_CAPTION


def test_starting_budget_is_nfbc_default():
    assert DEFAULT_STARTING_BUDGET == 1000
    curves = load_pacing_curves()
    assert curves["week"].min() == 1
    assert curves["week"].max() == 20
