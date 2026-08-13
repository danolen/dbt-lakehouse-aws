"""FAAB bid-bucket classification (#61 / The Process pp. 200–201).

Mirrors ``faab_bid_bucket`` / gap helpers in ``dbt/macros/faab_bid_bucket.sql``.
The Streamlit app reads ``bid_bucket`` from ``mart_faab_worksheet`` and only
formats it here — this module must not feed the lineup optimizer or FAAB
what-if scoring.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

import pandas as pd

DEFAULT_THRESHOLDS: dict[str, float] = {
    "cheap_high_bid_max": 5.0,
    "cheap_pct_of_faab_max": 2.0,
    "expensive_high_bid_min": 25.0,
    "expensive_pct_of_faab_min": 8.0,
    "borderline_high_bid_min": 15.0,
    "high_own_pct_min": 90.0,
    "scarce_fa_count_max": 3.0,
    "ros_value_keeper_min": 0.0,
}

BUCKET_EMOJI = {
    "triage": "🩹",
    "tactical": "🎯",
    "strategic": "🏆",
}

BUCKET_LABELS = {
    "triage": "🩹 Triage",
    "tactical": "🎯 Tactical",
    "strategic": "🏆 Strategic",
}

_PITCHER_TOKENS = frozenset({"P", "SP", "RP"})


def pos_tokens(position: Any) -> list[str]:
    if position is None:
        return []
    text = str(position).strip()
    if not text:
        return []
    return [p.strip().upper() for p in text.split(",") if p.strip()]


def _flag(value: Any) -> int:
    try:
        return 1 if int(value or 0) == 1 else 0
    except (TypeError, ValueError):
        return 0


def fills_roster_gap(
    tokens: Iterable[str],
    *,
    gap_c: Any = 0,
    gap_of: Any = 0,
    gap_mi: Any = 0,
    gap_ci: Any = 0,
    gap_p: Any = 0,
) -> int:
    token_set = {str(t).upper() for t in tokens}
    if _flag(gap_c) and "C" in token_set:
        return 1
    if _flag(gap_of) and "OF" in token_set:
        return 1
    if _flag(gap_mi) and ("2B" in token_set or "SS" in token_set):
        return 1
    if _flag(gap_ci) and ("1B" in token_set or "3B" in token_set):
        return 1
    if _flag(gap_p) and bool(token_set & _PITCHER_TOKENS):
        return 1
    return 0


def is_scarce_position(
    tokens: Iterable[str],
    *,
    scarce_c: Any = 0,
    scarce_of: Any = 0,
    scarce_mi: Any = 0,
    scarce_ci: Any = 0,
    scarce_p: Any = 0,
) -> int:
    return fills_roster_gap(
        tokens,
        gap_c=scarce_c,
        gap_of=scarce_of,
        gap_mi=scarce_mi,
        gap_ci=scarce_ci,
        gap_p=scarce_p,
    )


def gaps_from_counts(
    *,
    n_c: int,
    n_of: int,
    n_mi: int,
    n_ci: int,
    n_p: int,
    need_c: int = 2,
    need_of: int = 5,
    need_mi: int = 3,
    need_ci: int = 3,
    need_p: int = 9,
    has_my_owner: bool = True,
) -> dict[str, int]:
    if not has_my_owner:
        return {"gap_c": 0, "gap_of": 0, "gap_mi": 0, "gap_ci": 0, "gap_p": 0}
    return {
        "gap_c": int(n_c < need_c),
        "gap_of": int(n_of < need_of),
        "gap_mi": int(n_mi < need_mi),
        "gap_ci": int(n_ci < need_ci),
        "gap_p": int(n_p < need_p),
    }


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number:  # NaN
        return default
    return number


def classify_bid_bucket(
    *,
    has_faab: Any,
    has_ftn_rec: Any,
    high_bid: Any,
    high_bid_pct_of_faab: Any,
    own_pct: Any,
    ros_value: Any,
    fills_roster_gap: Any,
    is_scarce_position: Any,
    thresholds: Optional[Mapping[str, float]] = None,
) -> Optional[str]:
    """Mirror the SQL CASE in ``faab_bid_bucket``. First match wins."""
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    if _flag(has_faab) == 0:
        return None

    has_ftn = _flag(has_ftn_rec) == 1
    bid = _num(high_bid, 0.0)
    pct = _num(high_bid_pct_of_faab, 0.0)
    own = _num(own_pct, 0.0)
    ros = _num(ros_value, -999.0) if ros_value is not None else -999.0
    gap = _flag(fills_roster_gap) == 1
    scarce = _flag(is_scarce_position) == 1

    cheap_ftn = has_ftn and (
        bid <= t["cheap_high_bid_max"] or pct <= t["cheap_pct_of_faab_max"]
    )
    contested_unlisted = (not has_ftn) and (
        own >= t["high_own_pct_min"] and ros >= t["ros_value_keeper_min"]
    )
    unlisted_not_contested = (not has_ftn) and (not contested_unlisted)

    if gap and (cheap_ftn or unlisted_not_contested):
        return "triage"

    expensive_ftn = has_ftn and (
        bid >= t["expensive_high_bid_min"] or pct >= t["expensive_pct_of_faab_min"]
    )
    unpriced_keeper = (not has_ftn) and (
        own >= t["high_own_pct_min"] and ros >= t["ros_value_keeper_min"]
    )
    borderline_scarce = has_ftn and scarce and bid >= t["borderline_high_bid_min"]

    if expensive_ftn or unpriced_keeper or borderline_scarce:
        return "strategic"

    return "tactical"


def format_bid_bucket(bucket: Any) -> str:
    try:
        if bucket is None or pd.isna(bucket):
            return ""
    except (TypeError, ValueError):
        if bucket is None:
            return ""
    key = str(bucket).strip().lower()
    if not key or key in {"nan", "none", "<na>"}:
        return ""
    return BUCKET_LABELS.get(key, key)
