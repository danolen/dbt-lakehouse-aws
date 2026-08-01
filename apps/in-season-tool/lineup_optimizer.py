"""
Expected weekly lineup engine — v2 (#60).

Replaces the v1 greedy slot-order fill with an exact assignment solver, adds
pitcher selection, Monday-lock vs Friday-swap modes, optional category
weighting, and component-stat aggregates.

Design notes
------------
Solver: the hitter problem is a rectangular assignment problem (slots x
players), which has an exact polynomial solution. Rather than add SciPy to
``requirements.txt`` — which Streamlit Community Cloud installs on every
deploy — this module ships a self-contained Hungarian (Jonker-Volgenant
style) implementation. Rosters are <= ~60 players against <= 23 slots, so
runtime is well under a millisecond and adding a ~40 MB dependency for one
function is not justified. See ``_hungarian``.

Ineligible (player, slot) pairs get a large finite penalty instead of being
omitted, so the solver fills as many slots as possible first and maximizes
value second. Any assignment that lands on a penalty edge is reported as an
unfilled slot rather than a starter.

Determinism: players are pre-sorted by a total order before the matrix is
built, and the solver uses strict comparisons, so ties always resolve to the
same lineup for the same input.

Scoring: the neutral objective is the Razzball weekly dollar value, matching
v1. Passing ``weights`` switches to overall-points scoring, where each raw
unit is multiplied by ``overall_points_per_raw_unit`` from
``mart_overall_category_mobility`` (#205). Ratio categories (AVG/ERA/WHIP)
are linearized around the team's season-to-date numerators and denominators
supplied in ``ratio_context``; a week of volume is small relative to a
season, so the linearization is accurate near the current standing.

Lineup locks: NFBC locks pitchers for the whole week at the Monday deadline
and allows hitter-only swaps on Friday. ``mode='monday'`` selects hitters and
pitchers; ``mode='friday'`` re-optimizes hitters only and carries the
Monday pitcher set through untouched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

SLOT_FILL_ORDER = ["C", "SS", "2B", "3B", "1B", "OF", "MI", "CI", "UTIL"]

# Maps slot name -> pos_array tokens that satisfy it. UTIL accepts any hitter.
SLOT_ELIGIBILITY: dict[str, tuple[str, ...] | None] = {
    "C": ("C",),
    "1B": ("1B",),
    "2B": ("2B",),
    "3B": ("3B",),
    "SS": ("SS",),
    "OF": ("OF",),
    "MI": ("2B", "SS"),
    "CI": ("1B", "3B"),
    "UTIL": None,
}

PITCHER_SLOT = "P"

# Flex slots do not constrain position, so parking a multi-position player
# here preserves optionality elsewhere (Utility Advantage tie-break).
FLEX_SLOTS = frozenset({"UTIL", "MI", "CI"})

HITTER_COUNTING = ("r", "hr", "rbi", "sb")
PITCHER_COUNTING = ("k", "w", "sv")

# Raw-unit sizes matching mart_overall_category_mobility.raw_unit_size (#205).
RATIO_UNITS = {"avg": 0.001, "era": 0.01, "whip": 0.005}


@dataclass
class Assignment:
    slot: str
    player: dict[str, Any]


@dataclass
class LineupResult:
    starters: list[Assignment] = field(default_factory=list)
    bench: list[dict[str, Any]] = field(default_factory=list)
    unfilled_slots: list[str] = field(default_factory=list)
    total_score: float = 0.0
    totals: dict[str, float | None] = field(default_factory=dict)
    missing_projection_ids: list[Any] = field(default_factory=list)

    def starter_ids(self) -> set[Any]:
        return {a.player["nfbc_id"] for a in self.starters}

    def starter_keys(self) -> set[tuple[Any, str]]:
        return {_player_key(a.player) for a in self.starters}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_type(player: Mapping[str, Any]) -> str:
    rt = player.get("row_type")
    return str(rt) if rt else "hitter"


def _player_key(player: Mapping[str, Any]) -> tuple[Any, str]:
    """Two-way players appear once per role, so identity includes row_type."""
    return (player.get("nfbc_id"), _row_type(player))


def _num(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out != out:  # NaN
        return default
    return out


def _opt_num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _is_eligible(player: Mapping[str, Any], slot: str) -> bool:
    if slot == PITCHER_SLOT:
        return _row_type(player) == "pitcher"
    if _row_type(player) != "hitter":
        return False
    tokens = SLOT_ELIGIBILITY.get(slot)
    pos_array = player.get("pos_array") or []
    if tokens is None:
        return True
    return any(t in pos_array for t in tokens)


def _flexibility(player: Mapping[str, Any]) -> float:
    """Utility Advantage input: how many slots this player can fill.

    Callers may override with an explicit ``flex_score`` — that hook exists so
    late-start and injury-risk flexibility can be folded in once those fields
    are available upstream, without an API change.
    """
    override = _opt_num(player.get("flex_score"))
    if override is not None:
        return override
    if _row_type(player) == "pitcher":
        return 1.0
    return float(sum(1 for s in SLOT_ELIGIBILITY if _is_eligible(player, s)))


def _sort_key(player: Mapping[str, Any]) -> tuple:
    return (
        -_num(player.get("dollars")),
        -_num(player.get("dollars_per_game")),
        -_num(player.get("num_g")),
        str(player.get("nfbc_id")),
        _row_type(player),
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_player(
    player: Mapping[str, Any],
    *,
    weights: Mapping[str, float] | None = None,
    ratio_context: Mapping[str, float] | None = None,
    score_field: str = "dollars",
) -> float:
    """Neutral weekly value, or overall-points value when ``weights`` given.

    ``weights`` maps lowercase category -> overall points per raw unit, using
    the same unit convention as ``mart_overall_category_mobility``: 1 for
    counting stats, .001 for AVG, .01 for ERA, .005 for WHIP.
    """
    if not weights:
        return _num(player.get(score_field))

    ctx = ratio_context or {}
    total = 0.0
    if _row_type(player) == "hitter":
        for cat in HITTER_COUNTING:
            total += _num(player.get(cat)) * _num(weights.get(cat))
        total += _avg_contribution(player, weights, ctx)
    else:
        for cat in PITCHER_COUNTING:
            total += _num(player.get(cat)) * _num(weights.get(cat))
        total += _rate_contribution(player, weights, ctx, "era")
        total += _rate_contribution(player, weights, ctx, "whip")
    return total


def _avg_contribution(
    player: Mapping[str, Any],
    weights: Mapping[str, float],
    ctx: Mapping[str, float],
) -> float:
    weight = _num(weights.get("avg"))
    if not weight:
        return 0.0
    team_h = _opt_num(ctx.get("hits"))
    team_ab = _opt_num(ctx.get("at_bats"))
    if team_h is None or not team_ab:
        return 0.0
    ab = _num(player.get("ab"))
    hits = _num(player.get("hits"))
    if ab <= 0:
        return 0.0
    before = team_h / team_ab
    after = (team_h + hits) / (team_ab + ab)
    return ((after - before) / RATIO_UNITS["avg"]) * weight


def _rate_contribution(
    player: Mapping[str, Any],
    weights: Mapping[str, float],
    ctx: Mapping[str, float],
    cat: str,
) -> float:
    """ERA/WHIP are lower-is-better, so an improvement scores positive."""
    weight = _num(weights.get(cat))
    if not weight:
        return 0.0
    team_ip = _opt_num(ctx.get("innings_pitched"))
    if not team_ip:
        return 0.0
    ip = _num(player.get("ip"))
    if ip <= 0:
        return 0.0

    if cat == "era":
        team_num = _opt_num(ctx.get("earned_runs"))
        if team_num is None:
            return 0.0
        add = _num(player.get("er"))
        before = team_num * 9.0 / team_ip
        after = (team_num + add) * 9.0 / (team_ip + ip)
    else:
        team_num = _opt_num(ctx.get("walks_hits_allowed"))
        if team_num is None:
            return 0.0
        add = _num(player.get("hits_allowed")) + _num(player.get("walks_allowed"))
        before = team_num / team_ip
        after = (team_num + add) / (team_ip + ip)

    delta_units = (after - before) / RATIO_UNITS[cat]
    return -delta_units * weight


# ---------------------------------------------------------------------------
# Exact rectangular assignment (Hungarian / JV)
# ---------------------------------------------------------------------------


def _hungarian(cost: Sequence[Sequence[float]]) -> list[int]:
    """Minimize total cost. ``cost`` is n_rows x n_cols with n_rows <= n_cols.

    Returns ``assignment`` where ``assignment[row] = col``.
    """
    n = len(cost)
    if n == 0:
        return []
    m = len(cost[0])
    if m < n:
        raise ValueError("cost matrix must have at least as many columns as rows")

    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (m + 1)
    p = [0] * (m + 1)  # p[col] = row matched to col (1-indexed; 0 = free)
    way = [0] * (m + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1

    assignment = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            assignment[p[j] - 1] = j - 1
    return assignment


def _expand_slots(slot_counts: Mapping[str, int]) -> list[str]:
    """Deterministic slot list, one entry per open spot."""
    order = [*SLOT_FILL_ORDER, PITCHER_SLOT]
    slots: list[str] = []
    for slot in order:
        slots.extend([slot] * max(0, int(slot_counts.get(slot, 0) or 0)))
    for slot in sorted(set(slot_counts) - set(order)):
        slots.extend([slot] * max(0, int(slot_counts.get(slot, 0) or 0)))
    return slots


def _assign(
    players: list[dict[str, Any]],
    slots: list[str],
    scores: dict[tuple[Any, str], float],
    *,
    utility_advantage: bool,
) -> tuple[list[Assignment], list[str], list[dict[str, Any]]]:
    if not slots:
        return [], [], list(players)
    if not players:
        return [], list(slots), []

    max_abs = max((abs(s) for s in scores.values()), default=0.0)
    penalty = (max_abs + 1.0) * (len(slots) + 1.0) * 1000.0
    eps = (max_abs + 1.0) * 1e-9 if utility_advantage else 0.0

    n_rows, n_cols = len(slots), len(players)
    # Hungarian requires cols >= rows; pad with unusable columns when the
    # roster is shorter than the slot list so short rosters still solve.
    pad = max(0, n_rows - n_cols)

    cost: list[list[float]] = []
    for slot in slots:
        row = []
        for player in players:
            if _is_eligible(player, slot):
                value = scores[_player_key(player)]
                tie = 0.0
                if eps and slot not in FLEX_SLOTS and slot != PITCHER_SLOT:
                    # Prefer spending a low-flexibility player on an exact slot.
                    tie = eps * _flexibility(player)
                row.append(-value + tie)
            else:
                row.append(penalty)
        row.extend([penalty] * pad)
        cost.append(row)

    assignment = _hungarian(cost)

    starters: list[Assignment] = []
    unfilled: list[str] = []
    used: set[int] = set()
    for row_idx, col_idx in enumerate(assignment):
        slot = slots[row_idx]
        if col_idx < 0 or col_idx >= n_cols:
            unfilled.append(slot)
            continue
        player = players[col_idx]
        if not _is_eligible(player, slot):
            unfilled.append(slot)
            continue
        used.add(col_idx)
        starters.append(Assignment(slot=slot, player=player))

    bench = [p for i, p in enumerate(players) if i not in used]
    return starters, unfilled, bench


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def aggregate_totals(starters: Iterable[Assignment]) -> dict[str, float | None]:
    """Sum component stats. Ratios come from numerators/denominators."""
    totals: dict[str, float | None] = {
        "r": 0.0, "hr": 0.0, "rbi": 0.0, "sb": 0.0,
        "hits": 0.0, "ab": 0.0,
        "k": 0.0, "w": 0.0, "sv": 0.0,
        "ip": 0.0, "er": 0.0, "hits_allowed": 0.0, "walks_allowed": 0.0,
    }
    for a in starters:
        p = a.player
        if _row_type(p) == "hitter":
            for key in (*HITTER_COUNTING, "hits", "ab"):
                totals[key] = (totals[key] or 0.0) + _num(p.get(key))
        else:
            for key in (*PITCHER_COUNTING, "ip", "er", "hits_allowed", "walks_allowed"):
                totals[key] = (totals[key] or 0.0) + _num(p.get(key))

    ab = totals["ab"] or 0.0
    ip = totals["ip"] or 0.0
    totals["avg"] = (totals["hits"] / ab) if ab > 0 else None
    totals["era"] = ((totals["er"] * 9.0) / ip) if ip > 0 else None
    totals["whip"] = (
        ((totals["hits_allowed"] + totals["walks_allowed"]) / ip) if ip > 0 else None
    )
    return totals


def _missing_projection_ids(
    players: Iterable[Mapping[str, Any]], score_field: str, weights: Mapping[str, float] | None
) -> list[Any]:
    missing = []
    for p in players:
        if weights:
            keys = (
                (*HITTER_COUNTING, "ab")
                if _row_type(p) == "hitter"
                else (*PITCHER_COUNTING, "ip")
            )
            if all(_opt_num(p.get(k)) is None for k in keys):
                missing.append(p.get("nfbc_id"))
        elif _opt_num(p.get(score_field)) is None:
            missing.append(p.get("nfbc_id"))
    return missing


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def optimize_week(
    players: Iterable[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    *,
    mode: str = "monday",
    score_field: str | None = None,
    weights: Mapping[str, float] | None = None,
    ratio_context: Mapping[str, float] | None = None,
    locked_pitchers: Iterable[Mapping[str, Any]] | None = None,
    utility_advantage: bool = True,
) -> LineupResult:
    """Expected weekly lineup.

    mode='monday' assigns hitters and the nine P slots for the full week.
    mode='friday' re-optimizes hitters only (defaulting to weekend values) and
    carries ``locked_pitchers`` through unchanged, matching the NFBC rule that
    pitchers cannot be moved after Monday.
    """
    if mode not in ("monday", "friday"):
        raise ValueError(f"unknown mode: {mode}")

    if score_field is None:
        score_field = "dollars_friday_sunday" if mode == "friday" else "dollars"

    pool = [dict(p) for p in players]
    # Deduplicate on (nfbc_id, row_type); later duplicates are ignored.
    seen: set[tuple[Any, str]] = set()
    unique: list[dict[str, Any]] = []
    for p in pool:
        key = _player_key(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    unique.sort(key=_sort_key)

    counts = {k: int(v or 0) for k, v in slot_counts.items()}
    locked_list = [dict(p) for p in (locked_pitchers or [])]

    if mode == "friday":
        counts.pop(PITCHER_SLOT, None)
        candidates = [p for p in unique if _row_type(p) == "hitter"]
    else:
        candidates = unique

    scores = {
        _player_key(p): score_player(
            p, weights=weights, ratio_context=ratio_context, score_field=score_field
        )
        for p in candidates
    }

    slots = _expand_slots(counts)
    starters, unfilled, bench = _assign(
        candidates, slots, scores, utility_advantage=utility_advantage
    )

    result = LineupResult()
    result.starters = starters
    result.unfilled_slots = unfilled
    result.bench = bench

    if mode == "friday" and locked_list:
        for p in locked_list:
            result.starters.append(Assignment(slot=PITCHER_SLOT, player=p))

    result.total_score = sum(scores.get(_player_key(a.player), 0.0) for a in starters)
    result.totals = aggregate_totals(result.starters)
    result.missing_projection_ids = _missing_projection_ids(
        candidates, score_field, weights
    )
    result.bench.sort(key=_sort_key)
    return result


def optimize_lineup(
    players: Iterable[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    **kwargs: Any,
) -> LineupResult:
    """Backwards-compatible v1 entry point, now globally optimal.

    Same signature and return shape as the greedy v1 implementation, so
    existing callers keep working while gaining the exact assignment.
    """
    return optimize_week(players, slot_counts, **kwargs)


def simulate_add_drop(
    players: Iterable[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    *,
    add: Mapping[str, Any] | None = None,
    drop_key: tuple[Any, str] | None = None,
    **kwargs: Any,
) -> tuple[LineupResult, LineupResult]:
    """Return (baseline, what_if) lineups for an add/drop.

    The what-if roster runs through the same engine, so a bench-only
    acquisition correctly produces no change to the starting lineup.
    """
    roster = [dict(p) for p in players]
    baseline = optimize_week(roster, slot_counts, **kwargs)

    what_if_roster = [p for p in roster if _player_key(p) != drop_key] if drop_key else list(roster)
    if add is not None:
        what_if_roster.append(dict(add))
    what_if = optimize_week(what_if_roster, slot_counts, **kwargs)
    return baseline, what_if
