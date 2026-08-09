"""Projection rate divergence display helpers (#206).

Flags are observability metadata only — never feed ``optimize_week`` or
FAAB what-if scoring.

Lineup Optimizer Rate flags show hitter rate divergence only. Pitcher
``START`` / ``start_missed`` rows stay in the mart for after-the-fact
calibration but are hidden here — they are misleading when setting a
lineup before the week’s games.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

_FLAG_PRIORITY = {
    "extreme": 0,
    "elevated": 1,
    "depressed": 2,
    "insufficient_sample": 3,
    "unknown": 4,
    "in_line": 5,
}

# Pitcher start-occurrence flags are kept in the mart; not shown in the UI.
_UI_NOTABLE_FLAGS = frozenset({"elevated", "extreme", "depressed"})
_UI_HIDDEN_STATS = frozenset({"START"})


def classify_rate_divergence(
    *,
    projected_rate: Optional[float],
    season_rate: Optional[float],
    season_volume: Optional[float],
    elevated_ratio: float = 1.5,
    extreme_ratio: float = 2.0,
    min_sample_volume: float = 100.0,
) -> dict[str, Any]:
    """Mirror mart flag logic for unit tests / local checks."""
    if season_volume is None or season_volume < min_sample_volume:
        return {
            "divergence_ratio": None,
            "divergence_flag": "insufficient_sample",
            "min_sample_met": False,
        }
    if (
        projected_rate is None
        or season_rate is None
        or season_rate <= 0
        or projected_rate != projected_rate
        or season_rate != season_rate
    ):
        return {
            "divergence_ratio": None,
            "divergence_flag": "unknown",
            "min_sample_met": True,
        }
    ratio = float(projected_rate) / float(season_rate)
    if ratio >= extreme_ratio:
        flag = "extreme"
    elif ratio >= elevated_ratio:
        flag = "elevated"
    elif ratio <= (1.0 / elevated_ratio):
        flag = "depressed"
    else:
        flag = "in_line"
    return {
        "divergence_ratio": ratio,
        "divergence_flag": flag,
        "min_sample_met": True,
    }


def summarize_player_flags(
    divergence_df: pd.DataFrame,
    *,
    projection_slices: Optional[list[str]] = None,
) -> dict[Any, str]:
    """Map nfbc_id → short display string of notable hitter rate flags.

    Excludes ``START`` / start_missed rows (mart still computes them).
    """
    if divergence_df is None or divergence_df.empty:
        return {}
    df = divergence_df.copy()
    if "is_latest_projection" in df.columns:
        df = df[df["is_latest_projection"].fillna(False).astype(bool)]
    if projection_slices and "projection_slice" in df.columns:
        df = df[df["projection_slice"].isin(projection_slices)]
    if "stat" in df.columns:
        df = df[~df["stat"].astype(str).str.upper().isin(_UI_HIDDEN_STATS)]
    if df.empty or "nfbc_id" not in df.columns:
        return {}

    out: dict[Any, str] = {}
    for nfbc_id, grp in df.groupby("nfbc_id", dropna=False):
        parts: list[str] = []
        rows = grp.to_dict(orient="records")
        rows.sort(
            key=lambda r: (
                _FLAG_PRIORITY.get(str(r.get("divergence_flag")), 99),
                str(r.get("stat") or ""),
                str(r.get("projection_slice") or ""),
            )
        )
        for r in rows:
            flag = str(r.get("divergence_flag") or "")
            if flag not in _UI_NOTABLE_FLAGS:
                continue
            stat = r.get("stat") or "?"
            slice_ = r.get("projection_slice") or ""
            ratio = r.get("divergence_ratio")
            if ratio is not None and ratio == ratio:
                parts.append(f"{stat}/{slice_} {flag} ({float(ratio):.2f}x)")
            else:
                parts.append(f"{stat}/{slice_} {flag}")
        if parts:
            out[nfbc_id] = "; ".join(parts[:3])
            try:
                out[int(nfbc_id)] = out[nfbc_id]
            except (TypeError, ValueError):
                pass
    return out


def flag_caption() -> str:
    return (
        "**Rate flags** compare the vendor projection rate to season-to-date "
        "rate (same stat / AB). Thresholds are in seed "
        "`projection_divergence_thresholds` (default elevated ≥1.5×, extreme "
        "≥2.0×, min 100 AB). Pitcher start occurred/missed flags are computed "
        "in the mart but hidden here — they are after-the-fact and misleading "
        "when setting a lineup before the week. Flags are informational only "
        "— they do not change projections or the optimizer."
    )


__all__ = [
    "classify_rate_divergence",
    "flag_caption",
    "summarize_player_flags",
]
