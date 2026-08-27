"""FAAB budget pacing vs The Process 2025 Appendix p. 76 (#64).

Book curves are Elite-tier vs 1st-quartile *cumulative spend* for a $1,000
NFBC budget, FAAB weeks 2–20 (Adam Warner). This module plots those
reference bands plus a single current-week marker from remaining FAAB.
It must not invent a weekly personal spend line, and it must not feed
the lineup optimizer or FAAB what-if scoring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
import pandas as pd
import plotly.graph_objects as go

Number = Union[int, float]

DEFAULT_STARTING_BUDGET = 1000
DEFAULT_SCORING_PERIODS = 26
DEFAULT_SEASON_START = date(2026, 3, 27)
APPENDIX_LAST_WEEK = 20
APPENDIX_PAGE = "2025 Appendix p. 76"

PACING_CAPTION = (
    "FAAB pacing (*The Process* 2025 Appendix p. 76, Adam Warner): shaded "
    "band is Elite-tier vs 1st-quartile cumulative spend of a $1,000 NFBC "
    "budget (FAAB weeks 2–20). The marker is "
    "`starting_budget − my_faab_remaining` at the remaining-as-of week — "
    "not a weekly spend history. Burn/hoard compares remaining ÷ weeks left "
    "to the book-implied remaining at that week. Appendix sample ends week "
    "20; later weeks hold the week-20 curve. Does not feed the optimizer "
    "or FAAB what-if."
)

STATUS_OVERSPENDING = "overspending"
STATUS_ON_PACE = "on_pace"
STATUS_HOARDING = "hoarding"

STATUS_LABELS = {
    STATUS_OVERSPENDING: "Overspending vs Elite",
    STATUS_ON_PACE: "On pace (Elite–1st quartile)",
    STATUS_HOARDING: "Hoarding vs 1st quartile",
}

_SEED_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "faab_pacing_curves.csv",
    Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "faab_pacing_curves.csv",
)
_CALENDAR_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "dbt" / "seeds" / "season_scoring_calendar.csv",
    Path(__file__).resolve().parents[1] / "dbt" / "seeds" / "season_scoring_calendar.csv",
)


@dataclass(frozen=True)
class PacingSnapshot:
    week: int
    spent_to_date: int
    remaining: int
    weeks_remaining: int
    elite_spent: float
    q1_spent: float
    elite_remaining: float
    q1_remaining: float
    my_weekly_capacity: float
    elite_weekly_capacity: float
    q1_weekly_capacity: float
    status: str
    sample_ended: bool
    starting_budget: int
    as_of_date: Optional[str]


def _read_csv(candidates: tuple[Path, ...]) -> Optional[pd.DataFrame]:
    for path in candidates:
        if path.is_file():
            return pd.read_csv(path)
    return None


def load_pacing_curves() -> pd.DataFrame:
    """Elite / 1st-quartile cumulative spend by FAAB week from the seed."""
    df = _read_csv(_SEED_CANDIDATES)
    if df is None or df.empty:
        raise FileNotFoundError("faab_pacing_curves.csv not found")
    out = pd.DataFrame(
        {
            "week": pd.to_numeric(df["week"], errors="coerce"),
            "elite_cumulative_spend": pd.to_numeric(
                df["elite_cumulative_spend"], errors="coerce"
            ),
            "first_quartile_cumulative_spend": pd.to_numeric(
                df["first_quartile_cumulative_spend"], errors="coerce"
            ),
        }
    ).dropna()
    return out.sort_values("week").reset_index(drop=True)


def load_season_calendar() -> tuple[date, int]:
    df = _read_csv(_CALENDAR_CANDIDATES)
    if df is None or df.empty:
        return DEFAULT_SEASON_START, DEFAULT_SCORING_PERIODS
    start = pd.to_datetime(df["season_start_date"].iloc[0], errors="coerce")
    periods = pd.to_numeric(df["scoring_periods"].iloc[0], errors="coerce")
    season_start = start.date() if pd.notna(start) else DEFAULT_SEASON_START
    n_periods = (
        int(periods) if pd.notna(periods) else DEFAULT_SCORING_PERIODS
    )
    return season_start, n_periods


def parse_week_date(value: Any, *, season_year: int = 2026) -> Optional[date]:
    """Parse worksheet week_of / seed as_of into a date."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().date()
        except Exception:
            pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none", "n/a"}:
        return None
    # Bare M/D from Razzball week_of (e.g. "8/24") — pandas would invent year 1.
    if text.count("/") == 1 and "-" not in text:
        try:
            month_s, day_s = text.split("/")
            return date(season_year, int(month_s), int(day_s))
        except (TypeError, ValueError):
            return None
    ts = pd.to_datetime(text, errors="coerce")
    if pd.notna(ts):
        return ts.date()
    return None


def season_week_number(
    day: date,
    season_start: date = DEFAULT_SEASON_START,
    periods: int = DEFAULT_SCORING_PERIODS,
) -> int:
    elapsed = (day - season_start).days // 7 + 1
    return int(min(max(elapsed, 1), periods))


def spent_to_date(
    remaining: Optional[Number],
    starting_budget: int = DEFAULT_STARTING_BUDGET,
) -> Optional[int]:
    if remaining is None or (isinstance(remaining, float) and pd.isna(remaining)):
        return None
    rem = int(round(float(remaining)))
    if rem < 0:
        rem = 0
    return int(starting_budget - rem)


def curve_spend_at(curves: pd.DataFrame, week: int, column: str) -> float:
    """Linear interpolation on the appendix curve; hold the last sample week."""
    weeks = curves["week"].astype(float).to_numpy()
    spends = curves[column].astype(float).to_numpy()
    return float(np.interp(float(week), weeks, spends))


def classify_pace(remaining: float, elite_remaining: float, q1_remaining: float) -> str:
    """Compare remaining $ to book-implied remaining at this week.

    Elite spent more, so elite remaining is the lower bound of the band.
    Remaining below Elite → overspending; above 1st quartile → hoarding.
    """
    lo = min(elite_remaining, q1_remaining)
    hi = max(elite_remaining, q1_remaining)
    if remaining < lo:
        return STATUS_OVERSPENDING
    if remaining > hi:
        return STATUS_HOARDING
    return STATUS_ON_PACE


def pacing_snapshot(
    *,
    remaining: Optional[Number],
    weeks_remaining: Optional[Number],
    week: Optional[int],
    as_of_date: Optional[str] = None,
    starting_budget: int = DEFAULT_STARTING_BUDGET,
    curves: Optional[pd.DataFrame] = None,
) -> Optional[PacingSnapshot]:
    if remaining is None or (isinstance(remaining, float) and pd.isna(remaining)):
        return None
    rem = float(remaining)
    if rem <= 0:
        return None
    spent = spent_to_date(rem, starting_budget)
    if spent is None or week is None:
        return None
    wk = int(week)
    wr = int(weeks_remaining) if weeks_remaining is not None and not pd.isna(weeks_remaining) else None
    if wr is None or wr <= 0:
        wr = 1
    table = curves if curves is not None else load_pacing_curves()
    elite_spent = curve_spend_at(table, wk, "elite_cumulative_spend")
    q1_spent = curve_spend_at(table, wk, "first_quartile_cumulative_spend")
    elite_rem = starting_budget - elite_spent
    q1_rem = starting_budget - q1_spent
    return PacingSnapshot(
        week=wk,
        spent_to_date=int(spent),
        remaining=int(round(rem)),
        weeks_remaining=wr,
        elite_spent=elite_spent,
        q1_spent=q1_spent,
        elite_remaining=elite_rem,
        q1_remaining=q1_rem,
        my_weekly_capacity=rem / wr,
        elite_weekly_capacity=elite_rem / wr,
        q1_weekly_capacity=q1_rem / wr,
        status=classify_pace(rem, elite_rem, q1_rem),
        sample_ended=wk > APPENDIX_LAST_WEEK,
        starting_budget=starting_budget,
        as_of_date=as_of_date,
    )


def build_pacing_chart(snap: PacingSnapshot, curves: Optional[pd.DataFrame] = None) -> go.Figure:
    table = curves if curves is not None else load_pacing_curves()
    weeks = table["week"].tolist()
    elite = table["elite_cumulative_spend"].tolist()
    q1 = table["first_quartile_cumulative_spend"].tolist()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=weeks,
            y=elite,
            name="Elite",
            mode="lines",
            line=dict(color="#1f77b4", width=2),
            hovertemplate="Week %{x}: Elite $%{y:.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=weeks,
            y=q1,
            name="1st quartile",
            mode="lines",
            line=dict(color="#ff7f0e", width=2),
            fill="tonexty",
            fillcolor="rgba(31, 119, 180, 0.15)",
            hovertemplate="Week %{x}: 1st quartile $%{y:.0f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[snap.week],
            y=[snap.spent_to_date],
            name="You (remaining as of)",
            mode="markers",
            marker=dict(size=12, color="#d62728", symbol="diamond"),
            hovertemplate=(
                f"Week {snap.week}: spent ${snap.spent_to_date}"
                f" (${snap.remaining} left)<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        xaxis_title="FAAB week",
        yaxis_title="Cumulative spend ($)",
        yaxis=dict(range=[0, DEFAULT_STARTING_BUDGET]),
        xaxis=dict(range=[1, max(APPENDIX_LAST_WEEK, snap.week)]),
        title=dict(text="Budget pacing vs Elite / 1st quartile", font=dict(size=14)),
    )
    return fig


def marker_week(
    *,
    as_of_value: Any,
    week_of_value: Any,
    season_start: date = DEFAULT_SEASON_START,
    periods: int = DEFAULT_SCORING_PERIODS,
) -> Optional[int]:
    """Season week for the remaining-$ snapshot (as_of), else worksheet week_of."""
    season_year = season_start.year
    day = parse_week_date(as_of_value, season_year=season_year) or parse_week_date(
        week_of_value, season_year=season_year
    )
    if day is None:
        return None
    return season_week_number(day, season_start, periods)
