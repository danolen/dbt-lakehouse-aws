"""Theoretical FAAB bid (#62 / The Process p. 199).

Mirrors ``faab_theoretical_bid`` in ``dbt/macros/faab_theoretical_bid.sql``.
The Streamlit app prefers ``theoretical_bid`` from ``mart_faab_worksheet`` and
fills the same formula locally when that column is not built yet. Display
only — this module must not feed the lineup optimizer or FAAB what-if
scoring.

Book uses full-season waiver value × league FAAB allowance. Ticket #62 uses
remaining undrafted-value baseline × remaining budget (``my_faab_remaining``).
"""

from __future__ import annotations

from typing import Optional, Union

import pandas as pd

Number = Union[int, float]

# Keep in sync with dbt/seeds/faab_theoretical_bid_baseline.csv.
DEFAULT_REMAINING_UNDRAFTED_VALUE = {
    "oc": 350.0,
    "me": 450.0,
    "50s": 250.0,
}

THEORETICAL_BID_HELP = (
    "(positive RoS $ ÷ remaining undrafted-value baseline) × remaining FAAB. "
    "Framework from The Process p. 199 — noisy, not a recommended bid."
)

THEORETICAL_BID_CAPTION = (
    "Theoretical $ (*The Process* p. 199): (positive RoS $ / remaining "
    "undrafted-value baseline) × remaining FAAB. Baseline is a per-format "
    "placeholder in `dbt/seeds/faab_theoretical_bid_baseline.csv` — iterate "
    "with history. Noisy; not a recommended bid. Does not feed the lineup "
    "optimizer or FAAB what-if."
)


def theoretical_bid(
    ros_value: Optional[Number],
    remaining_budget: Optional[Number],
    remaining_undrafted_value: Optional[Number],
) -> Optional[int]:
    """Integer FAAB dollars, or None when the formula does not apply."""
    if remaining_budget is None or remaining_budget <= 0:
        return None
    if remaining_undrafted_value is None or remaining_undrafted_value <= 0:
        return None
    if ros_value is None:
        return None
    share = max(float(ros_value), 0.0) / float(remaining_undrafted_value)
    return int(round(share * float(remaining_budget)))


def attach_theoretical_bid(
    df: pd.DataFrame, league_format: Optional[str]
) -> pd.DataFrame:
    """Prefer the mart column; otherwise apply the same p. 199 formula locally.

    Lets the worksheet render Theoretical $ after an app deploy and before
    ``dbt build --select mart_faab_worksheet``. Once the mart column exists,
    that value wins (including nulls).
    """
    if df is None or df.empty:
        return df
    if "theoretical_bid" in df.columns:
        return df
    out = df.copy()
    denom = DEFAULT_REMAINING_UNDRAFTED_VALUE.get((league_format or "").strip().lower())
    ros = pd.to_numeric(out["ros_value"], errors="coerce") if "ros_value" in out.columns else None
    remaining = (
        pd.to_numeric(out["my_faab_remaining"], errors="coerce")
        if "my_faab_remaining" in out.columns
        else None
    )
    if ros is None or remaining is None:
        out["theoretical_bid"] = pd.Series([None] * len(out), dtype="Int64")
        return out

    bids: list[Optional[int]] = []
    for ros_v, rem_v in zip(ros, remaining):
        bids.append(
            theoretical_bid(
                None if pd.isna(ros_v) else float(ros_v),
                None if pd.isna(rem_v) else float(rem_v),
                denom,
            )
        )
    out["theoretical_bid"] = pd.Series(bids, index=out.index, dtype="Int64")
    return out
