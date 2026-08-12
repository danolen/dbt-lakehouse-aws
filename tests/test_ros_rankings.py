"""ROS rankings tab helpers (#67)."""

from __future__ import annotations

import pandas as pd
import pytest

from ros_rankings import (
    apply_ros_filters,
    format_for_league,
    format_ros_display,
    ros_table_name,
)


def test_format_for_league_maps_configured_leagues():
    cfg = pd.DataFrame(
        [
            {"league": "nolen_oc", "format": "oc"},
            {"league": "nolen_cash_15", "format": "me"},
            {"league": "nolen_50", "format": "50s"},
        ]
    )
    assert format_for_league(cfg, "nolen_oc") == "oc"
    assert format_for_league(cfg, "nolen_cash_15") == "me"
    assert format_for_league(cfg, "nolen_50") == "50s"
    assert ros_table_name("oc") == "mart_rest_of_season_overall_rankings_oc"
    assert format_for_league(cfg, "missing") is None


def test_apply_ros_filters_position_team_search():
    df = pd.DataFrame(
        [
            {
                "name": "Masyn Winn",
                "team": "STL",
                "pos": "SS",
                "projected_opening_day_status": "Starting",
            },
            {
                "name": "Yandy Diaz",
                "team": "TB",
                "pos": "1B",
                "projected_opening_day_status": "Starting",
            },
            {
                "name": "Lars Nootbaar",
                "team": "ARZ",
                "pos": "OF",
                "projected_opening_day_status": "Bench",
            },
        ]
    )
    ss = apply_ros_filters(df, positions=["SS"])
    assert list(ss["name"]) == ["Masyn Winn"]
    tb = apply_ros_filters(df, teams=["TB"])
    assert list(tb["name"]) == ["Yandy Diaz"]
    search = apply_ros_filters(df, search_name="noot")
    assert list(search["name"]) == ["Lars Nootbaar"]
    status = apply_ros_filters(df, statuses=["Bench"])
    assert list(status["name"]) == ["Lars Nootbaar"]


def test_multi_pos_matches_any_selected():
    df = pd.DataFrame([{"name": "Multi", "pos": "2B/SS", "team": "NYY"}])
    assert not apply_ros_filters(df, positions=["SS"]).empty
    assert apply_ros_filters(df, positions=["OF"]).empty


def test_format_ros_display_rounds_value():
    df = pd.DataFrame(
        [{"rank": 1, "name": "A", "value": 12.345, "avg": 0.2674, "era": 3.141}]
    )
    out = format_ros_display(df)
    assert out.iloc[0]["value"] == "$12.35"
    assert out.iloc[0]["avg"] == pytest.approx(0.267)
    assert out.iloc[0]["era"] == pytest.approx(3.14)
