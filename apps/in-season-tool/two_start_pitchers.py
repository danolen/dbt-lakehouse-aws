"""Two-start pitcher schedule buckets (#59).

Confidence is a plain-language label about how likely a projected two-start
is to hold, based on first-start day and the MLB team's games this week —

- Mon + full (7-game) week — most room for a Sunday second start
- Mon + short week — off day in the week makes the second start less certain
- Tue first — needs a full slate to come back Sunday
- Later first start (Wed–Sun) — not the classic Mon/Sun two-start pattern

Team game counts come from hitter ``num_g`` on the same MLB team in the
weekly lineup inputs. Book percentages are intentionally not shown.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import pandas as pd

# Razzball Opp codes → weekday label.
DAY_CODE_LABELS: dict[str, str] = {
    "MO": "Mon",
    "TU": "Tue",
    "WE": "Wed",
    "TH": "Thu",
    "FR": "Fri",
    "SA": "Sat",
    "SU": "Sun",
}

# Sort key: lower = more trustworthy for a classic two-start.
_BUCKET_SORT: dict[str, int] = {
    "mon_full": 0,
    "mon_short": 1,
    "mon_unknown": 2,
    "tue": 3,
    "later": 4,
    "unknown": 5,
}


def normalize_first_start_day(raw: Any) -> Optional[str]:
    """Return a two-letter day code (MO..SU) or None."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return None
    text = str(raw).strip().upper()
    if not text or text in ("NAN", "NONE", ""):
        return None
    if text in DAY_CODE_LABELS:
        return text
    aliases = {
        "MON": "MO",
        "MONDAY": "MO",
        "TUE": "TU",
        "TUES": "TU",
        "TUESDAY": "TU",
        "WED": "WE",
        "WEDNESDAY": "WE",
        "THU": "TH",
        "THUR": "TH",
        "THURS": "TH",
        "THURSDAY": "TH",
        "FRI": "FR",
        "FRIDAY": "FR",
        "SAT": "SA",
        "SATURDAY": "SA",
        "SUN": "SU",
        "SUNDAY": "SU",
    }
    return aliases.get(text)


def team_games_by_mlb_team(lineup_df: pd.DataFrame) -> dict[str, int]:
    """Map MLB team code → weekly games from hitter ``num_g`` (mode / max)."""
    if lineup_df is None or lineup_df.empty:
        return {}
    if "team" not in lineup_df.columns or "num_g" not in lineup_df.columns:
        return {}

    hitters = lineup_df
    if "row_type" in lineup_df.columns:
        hitters = lineup_df[
            lineup_df["row_type"].fillna("hitter").astype(str).str.lower() == "hitter"
        ]
    if hitters.empty:
        return {}

    out: dict[str, int] = {}
    for team, grp in hitters.groupby(hitters["team"].astype(str).str.strip()):
        if not team or team.lower() in ("nan", "none", ""):
            continue
        nums = pd.to_numeric(grp["num_g"], errors="coerce").dropna()
        if nums.empty:
            continue
        # Prefer the most common game count; fall back to max.
        mode = nums.mode()
        out[team] = int(mode.iloc[0]) if not mode.empty else int(nums.max())
    return out


def two_start_bucket(
    first_start_day: Any,
    team_games: Optional[int] = None,
) -> dict[str, Any]:
    """Classify a projected two-start into a schedule bucket.

    Returns ``bucket``, ``label``, ``day_code``, ``day_label``, ``team_games``,
    ``sort_key``.
    """
    code = normalize_first_start_day(first_start_day)
    day_label = DAY_CODE_LABELS.get(code or "", "—")

    games: Optional[int] = None
    if team_games is not None and team_games == team_games:
        try:
            games = int(team_games)
        except (TypeError, ValueError):
            games = None

    if code == "MO":
        if games is not None and games >= 7:
            bucket = "mon_full"
            label = "Mon · full week (7g)"
        elif games is not None and games > 0:
            label = f"Mon · short week ({games}g)"
            bucket = "mon_short"
        else:
            bucket = "mon_unknown"
            label = "Mon · week length unknown"
    elif code == "TU":
        bucket = "tue"
        if games is not None and games > 0:
            label = f"Tue first ({games}g week)"
        else:
            label = "Tue first"
    elif code in DAY_CODE_LABELS:
        bucket = "later"
        label = f"{day_label} first"
    else:
        bucket = "unknown"
        label = "Unknown first start"

    return {
        "bucket": bucket,
        "label": label,
        "day_code": code,
        "day_label": day_label,
        "team_games": games,
        "sort_key": _BUCKET_SORT.get(bucket, 99),
    }


def _is_free_agent(owner: Any) -> bool:
    if owner is None or (isinstance(owner, float) and owner != owner):
        return True
    return str(owner).strip() == ""


def build_two_start_rows(
    lineup_df: pd.DataFrame,
    *,
    selected_owner: Optional[str] = None,
    faab_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build display rows for my-roster + free-agent two-start pitchers.

    Sorted by schedule-bucket trust, then weekly projection dollars.
    Free-agent rows optionally join ``mart_faab_worksheet`` for FTN bids.
    """
    if lineup_df is None or lineup_df.empty:
        return pd.DataFrame()

    pitchers = lineup_df.copy()
    if "row_type" in pitchers.columns:
        pitchers = pitchers[
            pitchers["row_type"].fillna("hitter").astype(str).str.lower() == "pitcher"
        ]
    if "is_two_start" not in pitchers.columns:
        return pd.DataFrame()

    two_start = pitchers[pitchers["is_two_start"].fillna(False).astype(bool)].copy()
    if two_start.empty:
        return pd.DataFrame()

    def _status(owner: Any) -> str:
        if _is_free_agent(owner):
            return "Free agent"
        if selected_owner and str(owner).strip() == str(selected_owner).strip():
            return "My roster"
        return "Other roster"

    two_start["status"] = two_start["owner"].map(_status)
    two_start = two_start[two_start["status"].isin(["My roster", "Free agent"])]
    if two_start.empty:
        return pd.DataFrame()

    games_by_team = team_games_by_mlb_team(lineup_df)

    faab_by_id: dict[Any, Mapping[str, Any]] = {}
    if faab_df is not None and not faab_df.empty and "nfbc_id" in faab_df.columns:
        for _, row in faab_df.iterrows():
            nid = row.get("nfbc_id")
            if nid is None or (isinstance(nid, float) and nid != nid):
                continue
            as_map = row.to_dict()
            faab_by_id[nid] = as_map
            try:
                faab_by_id[int(nid)] = as_map
            except (TypeError, ValueError):
                pass

    records: list[dict[str, Any]] = []
    for _, row in two_start.iterrows():
        team = row.get("team")
        team_key = str(team).strip() if team is not None else ""
        team_games = games_by_team.get(team_key)
        bucket = two_start_bucket(row.get("first_start_day"), team_games)

        dollars = row.get("dollars")
        try:
            weekly_value = (
                float(dollars) if dollars is not None and dollars == dollars else None
            )
        except (TypeError, ValueError):
            weekly_value = None

        nid = row.get("nfbc_id")
        faab: Mapping[str, Any] = {}
        if nid in faab_by_id:
            faab = faab_by_id[nid]
        else:
            try:
                faab = faab_by_id.get(int(nid), {})
            except (TypeError, ValueError):
                faab = {}

        own_pct = row.get("own_pct")
        if own_pct is None:
            own_pct = faab.get("own_pct")

        records.append(
            {
                "status": row["status"],
                "player_name": row.get("player_name"),
                "team": team,
                "pos_raw": row.get("pos_raw"),
                "weekly_projection_value": weekly_value,
                "first_start_day": bucket["day_label"],
                "team_games": bucket["team_games"],
                "bucket": bucket["bucket"],
                "schedule_bucket": bucket["label"],
                "bucket_sort": bucket["sort_key"],
                "opps": row.get("opps") or row.get("pitcher_opp"),
                "own_pct": own_pct,
                "ros_value": row.get("ros_value"),
                "ftn_type": faab.get("ftn_type"),
                "low_bid": faab.get("low_bid"),
                "high_bid": faab.get("high_bid"),
                "nfbc_id": nid,
            }
        )

    out = pd.DataFrame.from_records(records)
    if out.empty:
        return out
    status_order = {"My roster": 0, "Free agent": 1}
    out["_status_ord"] = out["status"].map(status_order).fillna(9)
    out = out.sort_values(
        ["_status_ord", "bucket_sort", "weekly_projection_value"],
        ascending=[True, True, False],
        na_position="last",
    ).drop(columns=["_status_ord"])
    return out.reset_index(drop=True)


def schedule_bucket_caption() -> str:
    """Short caption for the Two-Start Pitchers section."""
    return (
        "**Schedule bucket** = how the first start lines up with the team's "
        "games count this week. Mon + full week is the cleanest path to a "
        "Sunday second start; Tue first usually needs all seven days; a Mon "
        "start on a 6-game week is shakier. Later first starts (Wed–Sun) are "
        "labeled separately. Team games come from weekly hitter `num_g`."
    )


__all__ = [
    "DAY_CODE_LABELS",
    "build_two_start_rows",
    "normalize_first_start_day",
    "schedule_bucket_caption",
    "team_games_by_mlb_team",
    "two_start_bucket",
]
