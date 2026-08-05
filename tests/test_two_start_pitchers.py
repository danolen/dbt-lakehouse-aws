"""Two-start pitcher schedule buckets (#59)."""

from __future__ import annotations

import pandas as pd
import pytest

from two_start_pitchers import (
    DAY_CODE_LABELS,
    build_two_start_rows,
    normalize_first_start_day,
    schedule_bucket_caption,
    team_games_by_mlb_team,
    two_start_bucket,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("MO", "MO"),
        ("mo", "MO"),
        ("Tuesday", "TU"),
        ("FRI", "FR"),
        (None, None),
        ("", None),
    ],
)
def test_normalize_first_start_day(raw, expected):
    assert normalize_first_start_day(raw) == expected


def test_mon_full_vs_short_vs_tue():
    full = two_start_bucket("MO", 7)
    assert full["bucket"] == "mon_full"
    assert "full week" in full["label"]
    assert "87%" not in full["label"]

    short = two_start_bucket("MO", 6)
    assert short["bucket"] == "mon_short"
    assert "6g" in short["label"]

    tue = two_start_bucket("TU", 7)
    assert tue["bucket"] == "tue"
    assert tue["sort_key"] > full["sort_key"]
    assert tue["sort_key"] > short["sort_key"]


def test_later_days_bucketed_without_percents():
    for code in ("WE", "TH", "FR", "SA", "SU"):
        b = two_start_bucket(code, 7)
        assert b["bucket"] == "later"
        assert "%" not in b["label"]
        assert DAY_CODE_LABELS[code] in b["label"]


def test_caption_has_no_book_percents():
    text = schedule_bucket_caption()
    assert "87%" not in text
    assert "68%" not in text
    assert "full week" in text.lower() or "Mon" in text


def test_team_games_from_hitters():
    lineup = pd.DataFrame(
        [
            {"row_type": "hitter", "team": "NYY", "num_g": 7},
            {"row_type": "hitter", "team": "NYY", "num_g": 7},
            {"row_type": "hitter", "team": "BOS", "num_g": 6},
            {"row_type": "pitcher", "team": "NYY", "num_g": None},
        ]
    )
    assert team_games_by_mlb_team(lineup) == {"NYY": 7, "BOS": 6}


def test_build_two_start_rows_schedule_buckets_and_fa_join():
    lineup = pd.DataFrame(
        [
            {
                "row_type": "hitter",
                "team": "NYY",
                "num_g": 7,
                "owner": "Nolen OC",
                "is_two_start": False,
                "player_name": "Hitter A",
                "nfbc_id": 99,
            },
            {
                "row_type": "hitter",
                "team": "PHI",
                "num_g": 6,
                "owner": "",
                "is_two_start": False,
                "player_name": "Hitter B",
                "nfbc_id": 98,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "Nolen OC",
                "player_name": "Cam Schlittler",
                "team": "NYY",
                "pos_raw": "SP",
                "dollars": 40.0,
                "first_start_day": "MO",
                "opps": "STL(MO) / ATL(SU)",
                "nfbc_id": 1,
                "own_pct": 80,
                "ros_value": 10.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "",
                "player_name": "Aaron Nola",
                "team": "PHI",
                "pos_raw": "SP",
                "dollars": 23.0,
                "first_start_day": "MO",
                "opps": "WSH(MO) / TOR(SA)",
                "nfbc_id": 2,
                "own_pct": 40,
                "ros_value": 15.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "Nolen OC",
                "player_name": "Joe Ryan",
                "team": "MIN",
                "pos_raw": "SP",
                "dollars": 47.0,
                "first_start_day": "TU",
                "opps": "@KC(TU) / @MIL(SU)",
                "nfbc_id": 3,
                "own_pct": 99,
                "ros_value": 20.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "Other Team",
                "player_name": "Hidden",
                "team": "SF",
                "pos_raw": "SP",
                "dollars": 50.0,
                "first_start_day": "MO",
                "opps": "x",
                "nfbc_id": 4,
                "own_pct": 90,
                "ros_value": 5.0,
            },
        ]
    )
    # MIN has no hitter rows → Tue with unknown games still buckets as tue
    faab = pd.DataFrame(
        [{"nfbc_id": 2, "low_bid": 5, "high_bid": 12, "ftn_type": "Streamer"}]
    )
    rows = build_two_start_rows(
        lineup, selected_owner="Nolen OC", faab_df=faab
    )
    assert list(rows["player_name"]) == [
        "Cam Schlittler",  # mon_full before tue despite lower $
        "Joe Ryan",
        "Aaron Nola",  # FA after my roster
    ]
    assert rows.iloc[0]["schedule_bucket"] == "Mon · full week (7g)"
    assert rows.iloc[1]["bucket"] == "tue"
    assert rows.iloc[2]["schedule_bucket"] == "Mon · short week (6g)"
    assert rows.iloc[2]["low_bid"] == 5
    assert "%" not in rows.iloc[0]["schedule_bucket"]
