"""Two-start pitcher confidence bands (#59)."""

from __future__ import annotations

import pandas as pd
import pytest

from two_start_pitchers import (
    ACCURACY_SOURCE_KIND,
    DAY_CODE_LABELS,
    bands_are_exhaustive,
    build_two_start_rows,
    confidence_tooltip_markdown,
    first_start_confidence,
    normalize_first_start_day,
)


def test_bands_cover_all_seven_days_exclusively():
    assert bands_are_exhaustive()
    bands = {code: first_start_confidence(code)["band"] for code in DAY_CODE_LABELS}
    # Every code resolves; no day left unknown.
    assert all(b != "unknown" for b in bands.values())
    # Mon / Tue / weekend distinctions from the ticket.
    assert first_start_confidence("MO")["emoji"] == "🟢"
    assert first_start_confidence("TU")["emoji"] == "🟡"
    assert first_start_confidence("SA")["emoji"] == "🔴"
    assert first_start_confidence("SU")["emoji"] == "🔴"
    # Wed–Fri assigned explicitly (not unlabelled).
    assert first_start_confidence("WE")["emoji"] == "🟡"
    assert first_start_confidence("TH")["emoji"] == "🟡"
    assert first_start_confidence("FR")["emoji"] == "🔴"


def test_no_day_matches_two_emoji_bands():
    """ mutually exclusive: each day code maps to exactly one emoji."""
    seen = {}
    for code in DAY_CODE_LABELS:
        emoji = first_start_confidence(code)["emoji"]
        assert code not in seen
        seen[code] = emoji
    assert len(seen) == 7


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


def test_accuracy_source_is_book_until_206():
    conf = first_start_confidence("MO")
    assert conf["accuracy_source_kind"] == "book"
    assert ACCURACY_SOURCE_KIND == "book"
    assert "book" in confidence_tooltip_markdown().lower()
    assert "p. 217" in confidence_tooltip_markdown() or "217" in confidence_tooltip_markdown()


def test_build_two_start_rows_my_roster_and_fa_only():
    lineup = pd.DataFrame(
        [
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "Nolen OC",
                "player_name": "Joe Ryan",
                "team": "MIN",
                "pos_raw": "SP",
                "dollars": 47.7,
                "first_start_day": "TU",
                "opps": "@KC(TU) / @MIL(SU)",
                "nfbc_id": 1,
                "own_pct": 99,
                "ros_value": 20.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "",
                "player_name": "Aaron Nola",
                "team": "PHI",
                "pos_raw": "SP",
                "dollars": 23.2,
                "first_start_day": "MO",
                "opps": "WSH(MO) / TOR(SA)",
                "nfbc_id": 2,
                "own_pct": 40,
                "ros_value": 15.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": True,
                "owner": "Other Team",
                "player_name": "Logan Webb",
                "team": "SF",
                "pos_raw": "SP",
                "dollars": 31.3,
                "first_start_day": "MO",
                "opps": "@TEX(MO) / DET(SU)",
                "nfbc_id": 3,
                "own_pct": 95,
                "ros_value": 25.0,
            },
            {
                "row_type": "pitcher",
                "is_two_start": False,
                "owner": "Nolen OC",
                "player_name": "One Start Guy",
                "team": "NYY",
                "pos_raw": "SP",
                "dollars": 50.0,
                "first_start_day": "FR",
                "opps": "BOS(FR)",
                "nfbc_id": 4,
                "own_pct": 80,
                "ros_value": 10.0,
            },
            {
                "row_type": "hitter",
                "is_two_start": False,
                "owner": "Nolen OC",
                "player_name": "Some Bat",
                "team": "LAD",
                "pos_raw": "OF",
                "dollars": 12.0,
                "first_start_day": None,
                "opps": None,
                "nfbc_id": 5,
                "own_pct": 90,
                "ros_value": 30.0,
            },
        ]
    )
    faab = pd.DataFrame(
        [
            {
                "nfbc_id": 2,
                "low_bid": 5,
                "high_bid": 12,
                "ftn_type": "Streamer",
                "own_pct": 40,
            }
        ]
    )
    rows = build_two_start_rows(
        lineup, selected_owner="Nolen OC", faab_df=faab
    )
    assert list(rows["player_name"]) == ["Joe Ryan", "Aaron Nola"]
    assert list(rows["status"]) == ["My roster", "Free agent"]
    assert rows.iloc[0]["confidence"].startswith("🟡")
    assert rows.iloc[1]["confidence"].startswith("🟢")
    assert rows.iloc[1]["low_bid"] == 5
    assert rows.iloc[1]["high_bid"] == 12
    assert rows.iloc[1]["ftn_type"] == "Streamer"
    assert rows.iloc[0]["weekly_projection_value"] == 47.7
