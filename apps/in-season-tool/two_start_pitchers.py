"""Two-start pitcher confidence bands and display rows (#59).

Bands key on **first-start day** (deterministic from Razzball Opp day codes).
Accuracy figures are book-sourced from *The Process* p. 217 until #206
replaces them with measured contest values.
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

# Book-sourced two-start completion accuracy (*The Process* p. 217).
# Mon / Tue / Sat–Sun are quoted; Wed–Thu share the Tue band; Fri is
# weekend-adjacent and shares the Sat/Sun band. Bands are mutually exclusive
# and jointly exhaustive over the seven day codes.
_BOOK_SOURCE = "book (*The Process* p. 217)"

# day_code -> (emoji, band_key, accuracy_display, band_label, accuracy_note)
_BAND_BY_DAY: dict[str, tuple[str, str, str, str, str]] = {
    "MO": ("🟢", "high", "87%", "Mon-first", _BOOK_SOURCE),
    "TU": ("🟡", "medium", "68%", "Tue-first", _BOOK_SOURCE),
    "WE": (
        "🟡",
        "medium",
        "~68%",
        "Wed-first (banded w/ Tue)",
        f"{_BOOK_SOURCE}; Wed not isolated in study",
    ),
    "TH": (
        "🟡",
        "medium",
        "~68%",
        "Thu-first (banded w/ Tue)",
        f"{_BOOK_SOURCE}; Thu not isolated in study",
    ),
    "FR": (
        "🔴",
        "low",
        "≤70%",
        "Fri-first (weekend-adjacent)",
        f"{_BOOK_SOURCE}; Fri banded with Sat/Sun",
    ),
    "SA": ("🔴", "low", "≤70%", "Sat-first", _BOOK_SOURCE),
    "SU": ("🔴", "low", "≤70%", "Sun-first", _BOOK_SOURCE),
}

ACCURACY_SOURCE_KIND = "book"  # flip to "measured" when #206 lands


def normalize_first_start_day(raw: Any) -> Optional[str]:
    """Return a two-letter day code (MO..SU) or None."""
    if raw is None or (isinstance(raw, float) and raw != raw):
        return None
    text = str(raw).strip().upper()
    if not text or text in ("NAN", "NONE", ""):
        return None
    # Already a code.
    if text in DAY_CODE_LABELS:
        return text
    # Full weekday name / abbreviation.
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


def first_start_confidence(first_start_day: Any) -> dict[str, Any]:
    """Map first-start day to a confidence band.

    Returns keys: day_code, day_label, emoji, band, accuracy, band_label,
    accuracy_source, accuracy_source_kind, confidence_display.
    Unknown / missing days get an explicit ``unknown`` band (not dual-matched).
    """
    code = normalize_first_start_day(first_start_day)
    if code is None or code not in _BAND_BY_DAY:
        return {
            "day_code": code,
            "day_label": DAY_CODE_LABELS.get(code or "", "—"),
            "emoji": "⚪",
            "band": "unknown",
            "accuracy": "—",
            "band_label": "unknown first-start day",
            "accuracy_source": _BOOK_SOURCE,
            "accuracy_source_kind": ACCURACY_SOURCE_KIND,
            "confidence_display": "⚪ unknown",
        }
    emoji, band, accuracy, band_label, source = _BAND_BY_DAY[code]
    return {
        "day_code": code,
        "day_label": DAY_CODE_LABELS[code],
        "emoji": emoji,
        "band": band,
        "accuracy": accuracy,
        "band_label": band_label,
        "accuracy_source": source,
        "accuracy_source_kind": ACCURACY_SOURCE_KIND,
        "confidence_display": f"{emoji} {DAY_CODE_LABELS[code]} ({accuracy})",
    }


def bands_are_exhaustive() -> bool:
    """True when every calendar day code has exactly one band mapping."""
    return set(_BAND_BY_DAY) == set(DAY_CODE_LABELS)


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

    Sorted by weekly projection dollars (``dollars`` / ``weekly_projection_value``)
    descending. Free-agent rows optionally join ``mart_faab_worksheet`` for
    FTN bid context.
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
    # Surface my roster + FA only (streaming / start-sit relevant).
    two_start = two_start[two_start["status"].isin(["My roster", "Free agent"])]
    if two_start.empty:
        return pd.DataFrame()

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
        conf = first_start_confidence(row.get("first_start_day"))
        dollars = row.get("dollars")
        try:
            weekly_value = float(dollars) if dollars is not None and dollars == dollars else None
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

        low_bid = faab.get("low_bid")
        high_bid = faab.get("high_bid")
        ftn_type = faab.get("ftn_type")
        own_pct = row.get("own_pct")
        if own_pct is None:
            own_pct = faab.get("own_pct")

        records.append(
            {
                "status": row["status"],
                "player_name": row.get("player_name"),
                "team": row.get("team"),
                "pos_raw": row.get("pos_raw"),
                "weekly_projection_value": weekly_value,
                "first_start_day": conf["day_label"],
                "confidence": conf["confidence_display"],
                "confidence_band": conf["band"],
                "accuracy": conf["accuracy"],
                "opps": row.get("opps") or row.get("pitcher_opp"),
                "own_pct": own_pct,
                "ros_value": row.get("ros_value"),
                "ftn_type": ftn_type,
                "low_bid": low_bid,
                "high_bid": high_bid,
                "nfbc_id": nid,
                "accuracy_source_kind": conf["accuracy_source_kind"],
            }
        )

    out = pd.DataFrame.from_records(records)
    if out.empty:
        return out
    # My roster first, then FA; within each, highest weekly $ first.
    status_order = {"My roster": 0, "Free agent": 1}
    out["_status_ord"] = out["status"].map(status_order).fillna(9)
    out = out.sort_values(
        ["_status_ord", "weekly_projection_value"],
        ascending=[True, False],
        na_position="last",
    ).drop(columns=["_status_ord"])
    return out.reset_index(drop=True)


def confidence_tooltip_markdown() -> str:
    """Streamlit caption / expander text for confidence bands."""
    kind = (
        "book-sourced (*The Process* p. 217), not measured on this contest"
        if ACCURACY_SOURCE_KIND == "book"
        else "measured from this contest's snapshots (#206)"
    )
    return (
        "**Confidence** keys on first-start day (Razzball Opp day code). "
        f"Accuracy figures are **{kind}**. "
        "🟢 Mon (87%) · 🟡 Tue–Thu (68% book Tue; Wed/Thu banded with Tue) · "
        "🔴 Fri–Sun (≤70% book weekend; Fri banded with Sat/Sun). "
        "Bands are mutually exclusive."
    )


__all__ = [
    "ACCURACY_SOURCE_KIND",
    "DAY_CODE_LABELS",
    "bands_are_exhaustive",
    "build_two_start_rows",
    "confidence_tooltip_markdown",
    "first_start_confidence",
    "normalize_first_start_day",
]
