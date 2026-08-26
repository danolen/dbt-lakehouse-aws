"""Theoretical FAAB bid (#62 / The Process p. 199).

Mirrors ``faab_theoretical_bid`` in ``dbt/macros/faab_theoretical_bid.sql``.
The Streamlit app reads ``theoretical_bid`` from ``mart_faab_worksheet`` and
only displays it — this module must not feed the lineup optimizer or FAAB
what-if scoring.

Book uses full-season waiver value × league FAAB allowance. Ticket #62 uses
remaining undrafted-value baseline × remaining budget (``my_faab_remaining``).
"""

from __future__ import annotations

from typing import Optional, Union

Number = Union[int, float]

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
