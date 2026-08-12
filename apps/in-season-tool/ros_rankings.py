"""ROS rankings helpers for the in-season tool (#67).

Maps a configured league to ``mart_rest_of_season_overall_rankings_{oc,me,50s}``
and applies the same position / team / opening-day / name filters as the
draft tool's preseason rankings view (without DynamoDB draft tracking).
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

import pandas as pd

ROS_FORMATS = ("oc", "me", "50s")

ROS_COLUMNS = [
    "rank",
    "id",
    "name",
    "team",
    "pos",
    "adp",
    "min_pick",
    "max_pick",
    "rank_diff",
    "projected_opening_day_status",
    "value",
    "pa",
    "ab",
    "r",
    "hr",
    "rbi",
    "sb",
    "avg",
    "obp",
    "slg",
    "ip",
    "k",
    "w",
    "sv",
    "era",
    "whip",
]


def format_for_league(league_cfg: pd.DataFrame, league_key: str) -> Optional[str]:
    """Return ``oc`` / ``me`` / ``50s`` from ``league_config``, or None."""
    if league_cfg is None or league_cfg.empty or "league" not in league_cfg.columns:
        return None
    if "format" not in league_cfg.columns:
        return None
    rows = league_cfg.loc[league_cfg["league"] == league_key]
    if rows.empty:
        return None
    fmt = str(rows.iloc[0]["format"] or "").strip().lower()
    if fmt not in ROS_FORMATS:
        return None
    return fmt


def ros_table_name(fmt: str) -> str:
    if fmt not in ROS_FORMATS:
        raise ValueError(f"unknown ROS format: {fmt}")
    return f"mart_rest_of_season_overall_rankings_{fmt}"


def _position_tokens(raw: Any) -> set[str]:
    if raw is None or (isinstance(raw, float) and raw != raw):
        return set()
    text = str(raw).replace("/", ",")
    return {p.strip() for p in text.split(",") if p.strip()}


def apply_ros_filters(
    df: pd.DataFrame,
    *,
    positions: Optional[Iterable[str]] = None,
    teams: Optional[Iterable[str]] = None,
    statuses: Optional[Iterable[str]] = None,
    search_name: str = "",
) -> pd.DataFrame:
    """Filter ROS rankings the way the draft tool filters preseason rankings."""
    if df is None or df.empty:
        return df
    out = df
    pos_sel = [p for p in (positions or []) if p]
    if pos_sel and "pos" in out.columns:
        wanted = set(pos_sel)
        mask = out["pos"].map(lambda v: bool(_position_tokens(v) & wanted))
        out = out.loc[mask]
    team_sel = [t for t in (teams or []) if t]
    if team_sel and "team" in out.columns:
        out = out.loc[out["team"].isin(team_sel)]
    status_sel = [s for s in (statuses or []) if s]
    if status_sel and "projected_opening_day_status" in out.columns:
        out = out.loc[out["projected_opening_day_status"].isin(status_sel)]
    q = (search_name or "").strip()
    if q and "name" in out.columns:
        out = out.loc[out["name"].astype(str).str.contains(q, case=False, na=False)]
    return out


def format_ros_display(df: pd.DataFrame) -> pd.DataFrame:
    """Round / format columns to match the draft-tool rankings table."""
    if df is None or df.empty:
        return df
    display = df.copy()
    available = [c for c in ROS_COLUMNS if c in display.columns]
    display = display[available]
    for col in ("pa", "ab", "r", "hr", "rbi", "sb", "ip", "k", "w", "sv"):
        if col in display.columns:
            display[col] = display[col].round(0).astype("Int64")
    for col in ("avg", "obp", "slg"):
        if col in display.columns:
            display[col] = display[col].round(3)
    for col in ("era", "whip"):
        if col in display.columns:
            display[col] = display[col].round(2)
    if "value" in display.columns:
        display["value"] = display["value"].apply(
            lambda x: f"${float(x):,.2f}" if pd.notna(x) and pd.notnull(x) else ""
        )
    return display


__all__ = [
    "ROS_COLUMNS",
    "ROS_FORMATS",
    "apply_ros_filters",
    "format_for_league",
    "format_ros_display",
    "ros_table_name",
]
