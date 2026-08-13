"""Default the in-season team pickers to a %nolen% roster / standings name.

Used by Lineup Optimizer, Overall Standings, and FAAB what-if. The user can
still change the selectbox; widget keys are league-scoped so switching
leagues does not keep another league's team.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

# Same substring as seed faab_bid_bucket_thresholds.owner_name_pattern.
MY_TEAM_SUBSTRING = "nolen"


def matches_my_team(name: Any, needle: str = MY_TEAM_SUBSTRING) -> bool:
    if name is None:
        return False
    text = str(name).strip()
    if not text:
        return False
    return needle.lower() in text.lower()


def matching_index(
    options: Sequence[Any],
    *,
    needle: str = MY_TEAM_SUBSTRING,
    aliases: Optional[Mapping[Any, Any]] = None,
) -> Optional[int]:
    """Index of the first option whose label (or alias) matches ``needle``."""
    if not options:
        return None
    needle_l = needle.lower()
    for i, opt in enumerate(options):
        blob = str(opt) if opt is not None else ""
        if aliases is not None and opt in aliases and aliases[opt] is not None:
            blob = f"{blob} {aliases[opt]}"
        if needle_l in blob.lower():
            return i
    return None


def default_index(
    options: Sequence[Any],
    *,
    needle: str = MY_TEAM_SUBSTRING,
    aliases: Optional[Mapping[Any, Any]] = None,
) -> int:
    """Like ``matching_index``, but 0 when nothing matches (selectbox default)."""
    found = matching_index(options, needle=needle, aliases=aliases)
    return 0 if found is None else found
