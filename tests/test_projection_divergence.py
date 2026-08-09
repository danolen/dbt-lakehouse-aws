"""Projection rate divergence flag logic (#206)."""

from __future__ import annotations

import pandas as pd
import pytest

from projection_divergence import classify_rate_divergence, summarize_player_flags


def test_garcia_weekend_sb_elevated():
    # Issue #206: 0.20 SB / 10 AB vs 4 SB / 350 AB ≈ 1.75x → elevated
    projected_rate = 0.20 / 10.0
    season_rate = 4.0 / 350.0
    result = classify_rate_divergence(
        projected_rate=projected_rate,
        season_rate=season_rate,
        season_volume=350.0,
        elevated_ratio=1.5,
        extreme_ratio=2.0,
        min_sample_volume=100.0,
    )
    assert result["divergence_flag"] == "elevated"
    assert result["divergence_ratio"] == pytest.approx(1.75, rel=0.02)


def test_yandy_weekend_sb_in_line():
    projected_rate = 0.06 / 11.0
    season_rate = 2.0 / 403.0
    result = classify_rate_divergence(
        projected_rate=projected_rate,
        season_rate=season_rate,
        season_volume=403.0,
        elevated_ratio=1.5,
        extreme_ratio=2.0,
        min_sample_volume=100.0,
    )
    assert result["divergence_flag"] == "in_line"
    assert 1.0 < result["divergence_ratio"] < 1.3


def test_insufficient_sample_not_flagged():
    result = classify_rate_divergence(
        projected_rate=0.05,
        season_rate=0.01,
        season_volume=50.0,
        min_sample_volume=100.0,
    )
    assert result["divergence_flag"] == "insufficient_sample"


def test_extreme_at_two_x():
    result = classify_rate_divergence(
        projected_rate=0.04,
        season_rate=0.02,
        season_volume=200.0,
        elevated_ratio=1.5,
        extreme_ratio=2.0,
    )
    assert result["divergence_flag"] == "extreme"


def test_summarize_player_flags_picks_notable():
    df = pd.DataFrame(
        [
            {
                "nfbc_id": 10279,
                "stat": "SB",
                "projection_slice": "weekend",
                "divergence_flag": "elevated",
                "divergence_ratio": 1.75,
                "is_latest_projection": True,
            },
            {
                "nfbc_id": 10279,
                "stat": "HR",
                "projection_slice": "weekend",
                "divergence_flag": "in_line",
                "divergence_ratio": 1.1,
                "is_latest_projection": True,
            },
            {
                "nfbc_id": 1,
                "stat": "SB",
                "projection_slice": "weekend",
                "divergence_flag": "elevated",
                "divergence_ratio": 1.6,
                "is_latest_projection": False,
            },
        ]
    )
    summary = summarize_player_flags(df, projection_slices=["weekend", "weekly"])
    assert 10279 in summary
    assert "SB/weekend elevated" in summary[10279]
    assert 1 not in summary  # not latest


def test_summarize_hides_start_missed_flags():
    """START/start_missed stays in the mart but not in Lineup Optimizer UI."""
    df = pd.DataFrame(
        [
            {
                "nfbc_id": 999,
                "stat": "START",
                "projection_slice": "weekly",
                "divergence_flag": "start_missed",
                "divergence_ratio": None,
                "is_latest_projection": True,
            },
            {
                "nfbc_id": 999,
                "stat": "SB",
                "projection_slice": "weekly",
                "divergence_flag": "elevated",
                "divergence_ratio": 1.8,
                "is_latest_projection": True,
            },
            {
                "nfbc_id": 888,
                "stat": "START",
                "projection_slice": "weekly",
                "divergence_flag": "start_missed",
                "divergence_ratio": None,
                "is_latest_projection": True,
            },
        ]
    )
    summary = summarize_player_flags(df, projection_slices=["weekly"])
    assert 999 in summary
    assert "SB/weekly elevated" in summary[999]
    assert "START" not in summary[999]
    assert "start_missed" not in summary[999]
    assert 888 not in summary  # START-only player → no UI flags
