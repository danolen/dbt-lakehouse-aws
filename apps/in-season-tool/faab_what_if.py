"""FAAB what-if: add/drop impact on expected weekly category totals (#187).

Wraps ``lineup_optimizer.simulate_add_drop_split_week`` so a candidate is
valued by the change to the team's optimized starters across the full NFBC
week — Monday lock (Mon–Thu hitters + week pitchers) then Friday hitter swap
(Fri–Sun) with pitchers locked. Bench-only adds correctly report zero
immediate lineup impact.

Overall-points estimates and noise-floor ties use columns already present on
``mart_weekly_category_plan`` (from #186 / mobility).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

from lineup_optimizer import LineupResult, optimize_week, simulate_add_drop_split_week
from weekly_category_plan import (
    CATEGORY_ORDER,
    gap_is_meaningful,
    noise_floor_raw,
    projection_for_category,
)

UNCERTAINTY_WITHIN_NOISE = "within_noise"
UNCERTAINTY_CLEAR = "clear_of_noise"
UNCERTAINTY_UNKNOWN = "unknown"

RANK_MODE_WEEKLY = "weekly_value"
RANK_MODE_OVERALL = "overall_pts"


@dataclass
class CategoryDelta:
    category: str
    baseline: Optional[float]
    what_if: Optional[float]
    delta_raw: Optional[float]
    overall_points_per_raw_unit: Optional[float]
    delta_overall_pts_estimate: Optional[float]
    noise_floor_raw: Optional[float]
    uncertainty: str  # within_noise | clear_of_noise | unknown
    is_ratio: bool = False


@dataclass
class WhatIfResult:
    ok: bool
    message: str
    add_nfbc_id: Any = None
    drop_nfbc_id: Any = None
    drop_row_type: Optional[str] = None
    drop_suggested: bool = False
    baseline: Optional[LineupResult] = None  # Monday lock
    what_if: Optional[LineupResult] = None  # Monday lock
    baseline_friday: Optional[LineupResult] = None
    what_if_friday: Optional[LineupResult] = None
    net_weekly_value: float = 0.0
    category_deltas: list[CategoryDelta] = field(default_factory=list)
    net_overall_pts_estimate: Optional[float] = None
    any_within_noise: bool = False
    bench_only_add: bool = False
    starts_monday_only: bool = False
    starts_friday_only: bool = False


def _row_type(player: Mapping[str, Any]) -> str:
    rt = player.get("row_type")
    return str(rt) if rt else "hitter"


def _player_key(player: Mapping[str, Any]) -> tuple[Any, str]:
    return (player.get("nfbc_id"), _row_type(player))


def _find_player(
    players: Iterable[Mapping[str, Any]],
    nfbc_id: Any,
    row_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    target = str(nfbc_id)
    for p in players:
        if str(p.get("nfbc_id")) != target:
            continue
        if row_type is not None and _row_type(p) != row_type:
            continue
        return dict(p)
    return None


def _finite(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _fmt_count(value: Any, decimals: int = 1) -> Optional[str]:
    num = _finite(value)
    if num is None:
        return None
    if abs(num - round(num)) < 1e-9:
        return str(int(round(num)))
    return f"{num:.{decimals}f}"


def _fmt_avg(value: Any) -> Optional[str]:
    num = _finite(value)
    if num is None:
        return None
    rendered = f"{num:.3f}"
    if rendered.startswith("0"):
        rendered = rendered[1:]
    return rendered


def _fmt_rate(value: Any, decimals: int = 2) -> Optional[str]:
    num = _finite(value)
    if num is None:
        return None
    return f"{num:.{decimals}f}"


def _join_stat_parts(parts: Sequence[Optional[str]]) -> str:
    return " · ".join(p for p in parts if p)


def format_projected_stats(player: Mapping[str, Any]) -> str:
    """Weekly projection line for ranking tables.

    Hitters: R, HR, RBI, SB, AVG. Pitchers: GS (if starts), IP, W, SV
    (if projected), K, ERA, WHIP. Missing pieces are omitted.
    """
    if _row_type(player) == "pitcher":
        gs = _finite(player.get("gs"))
        sv = _finite(player.get("sv"))
        parts = [
            f"{_fmt_count(gs, 0)} GS" if gs and gs > 0 else None,
            f"{_fmt_count(player.get('ip'))} IP" if _finite(player.get("ip")) is not None else None,
            f"{_fmt_count(player.get('w'))} W" if _finite(player.get("w")) is not None else None,
            f"{_fmt_count(sv)} SV" if sv is not None and sv > 0 else None,
            f"{_fmt_count(player.get('k'))} K" if _finite(player.get("k")) is not None else None,
            f"{_fmt_rate(player.get('era'))} ERA" if _finite(player.get("era")) is not None else None,
            f"{_fmt_rate(player.get('whip'))} WHIP" if _finite(player.get("whip")) is not None else None,
        ]
        return _join_stat_parts(parts)

    avg = player.get("batting_avg")
    if _finite(avg) is None:
        avg = player.get("avg")
    if _finite(avg) is None:
        hits = _finite(player.get("hits"))
        ab = _finite(player.get("ab"))
        if hits is not None and ab and ab > 0:
            avg = hits / ab
    parts = [
        f"{_fmt_count(player.get('r'))} R" if _finite(player.get("r")) is not None else None,
        f"{_fmt_count(player.get('hr'))} HR" if _finite(player.get("hr")) is not None else None,
        f"{_fmt_count(player.get('rbi'))} RBI" if _finite(player.get("rbi")) is not None else None,
        f"{_fmt_count(player.get('sb'))} SB" if _finite(player.get("sb")) is not None else None,
        f"{_fmt_avg(avg)} AVG" if _finite(avg) is not None else None,
    ]
    return _join_stat_parts(parts)


def _dollars(player: Mapping[str, Any]) -> float:
    for key in ("dollars_monday_thursday", "dollars", "dollars_friday_sunday"):
        val = player.get(key)
        try:
            if val is not None and val == val:  # not NaN
                return float(val)
        except (TypeError, ValueError):
            continue
    return 0.0


def starters_table(
    result: LineupResult, *, dollar_field: str = "dollars_monday_thursday"
) -> list[dict[str, Any]]:
    """Inspectable starter rows for UI / tests."""
    rows: list[dict[str, Any]] = []
    for a in result.starters:
        p = a.player
        dol = p.get(dollar_field)
        try:
            dol_f = float(dol) if dol is not None and dol == dol else _dollars(p)
        except (TypeError, ValueError):
            dol_f = _dollars(p)
        rows.append(
            {
                "slot": a.slot,
                "nfbc_id": p.get("nfbc_id"),
                "player_name": p.get("player_name"),
                "row_type": _row_type(p),
                "pos_raw": p.get("pos_raw"),
                "dollars": dol_f,
            }
        )
    return rows


def _plan_lookup(
    plan_rows: Optional[Sequence[Mapping[str, Any]]],
) -> dict[str, Mapping[str, Any]]:
    if not plan_rows:
        return {}
    return {str(r["category"]).upper(): r for r in plan_rows if r.get("category")}


def compute_category_deltas(
    baseline_totals: Mapping[str, Any],
    what_if_totals: Mapping[str, Any],
    plan_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> tuple[list[CategoryDelta], Optional[float], bool]:
    """Net category deltas using aggregate ratio numerators/denominators.

    Counting stats: what_if - baseline on the summed projection.
    Ratios: difference of rates recomputed from summed H/AB, ER/IP, (H+BB)/IP
    (already how split-week aggregates build AVG/ERA/WHIP).
    """
    by_cat = _plan_lookup(plan_rows)
    deltas: list[CategoryDelta] = []
    net_overall: Optional[float] = 0.0 if by_cat else None
    any_within = False

    for cat in CATEGORY_ORDER:
        baseline = projection_for_category(cat, baseline_totals)
        what_if = projection_for_category(cat, what_if_totals)
        if baseline is None and what_if is None:
            delta_raw = None
        elif baseline is None:
            delta_raw = what_if
        elif what_if is None:
            delta_raw = -baseline
        else:
            delta_raw = float(what_if) - float(baseline)

        plan = by_cat.get(cat, {})
        is_ratio = bool(plan.get("is_ratio", cat in ("AVG", "ERA", "WHIP")))
        pts_per = plan.get("overall_points_per_raw_unit")
        try:
            pts_per_f = float(pts_per) if pts_per is not None else None
        except (TypeError, ValueError):
            pts_per_f = None

        floor = plan.get("noise_floor_raw")
        if floor is None and plan:
            floor = noise_floor_raw(
                tie_cluster_raw_width=plan.get("tie_cluster_raw_width"),
                raw_unit_size=plan.get("raw_unit_size"),
            )
        try:
            floor_f = float(floor) if floor is not None else None
        except (TypeError, ValueError):
            floor_f = None

        d_pts: Optional[float] = None
        if delta_raw is not None and pts_per_f is not None and net_overall is not None:
            signed = (
                -float(delta_raw)
                if cat in ("ERA", "WHIP")
                else float(delta_raw)
            )
            d_pts = signed * abs(pts_per_f)
            net_overall += d_pts

        uncertainty = UNCERTAINTY_UNKNOWN
        if delta_raw is not None and floor_f is not None:
            if gap_is_meaningful(delta_raw, floor_f):
                uncertainty = UNCERTAINTY_CLEAR
            else:
                uncertainty = UNCERTAINTY_WITHIN_NOISE
                any_within = True

        deltas.append(
            CategoryDelta(
                category=cat,
                baseline=baseline,
                what_if=what_if,
                delta_raw=delta_raw,
                overall_points_per_raw_unit=pts_per_f,
                delta_overall_pts_estimate=d_pts,
                noise_floor_raw=floor_f,
                uncertainty=uncertainty,
                is_ratio=is_ratio,
            )
        )

    return deltas, net_overall, any_within


def suggest_drop(
    roster: Sequence[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    add: Mapping[str, Any],
    **optimize_kwargs: Any,
) -> tuple[Optional[tuple[Any, str]], str]:
    """Suggest a drop key ``(nfbc_id, row_type)``.

    Prefers the lowest-$ owned player who remains on the bench after the add
    is kept (no drop) across *both* Monday and Friday windows. Falls back to
    the lowest-$ owned player overall.
    """
    if not roster:
        return None, "No owned players to drop."

    add_key = _player_key(add)
    kw = {k: v for k, v in optimize_kwargs.items() if k != "mode"}
    with_add = list(roster) + [dict(add)]
    monday = optimize_week(with_add, slot_counts, mode="monday", **kw)
    friday = optimize_week(
        with_add,
        slot_counts,
        mode="friday",
        locked_pitchers=[
            dict(a.player) for a in monday.starters if a.slot == "P"
        ],
        **kw,
    )
    starter_keys = monday.starter_keys() | {
        k for k in friday.starter_keys() if k[1] == "hitter"
    }

    owned = [dict(p) for p in roster if _player_key(p) != add_key]
    if not owned:
        return None, "No owned players to drop."

    bench = [p for p in owned if _player_key(p) not in starter_keys]
    pool = bench if bench else owned
    pool_sorted = sorted(pool, key=lambda p: (_dollars(p), str(p.get("nfbc_id"))))
    pick = pool_sorted[0]
    key = _player_key(pick)
    label = "bench both halves after add" if bench else "lowest-$ owned"
    return key, (
        f"Suggested drop: {pick.get('player_name') or key[0]} "
        f"({label}; ${_dollars(pick):.1f})"
    )


def analyze_add_drop(
    roster: Sequence[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    *,
    add: Optional[Mapping[str, Any]] = None,
    add_nfbc_id: Any = None,
    add_row_type: Optional[str] = None,
    free_agents: Optional[Sequence[Mapping[str, Any]]] = None,
    drop_key: Optional[tuple[Any, str]] = None,
    drop_nfbc_id: Any = None,
    drop_row_type: Optional[str] = None,
    auto_suggest_drop: bool = True,
    plan_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    **optimize_kwargs: Any,
) -> WhatIfResult:
    """Baseline vs what-if lineups with category / overall-point deltas.

    Runs Monday lock then Friday hitter re-optimize for both rosters so a
    pickup started only Mon–Thu (or only Fri–Sun) is valued correctly.
    """
    add_player = dict(add) if add is not None else None
    if add_player is None:
        pool = list(free_agents or []) + list(roster)
        add_player = _find_player(pool, add_nfbc_id, add_row_type)
    if add_player is None:
        return WhatIfResult(
            ok=False,
            message=(
                f"Candidate nfbc_id={add_nfbc_id!r} not found among free agents "
                "(unmatched or empty candidate)."
            ),
            add_nfbc_id=add_nfbc_id,
        )

    resolved_drop = drop_key
    drop_suggested = False
    if resolved_drop is None and drop_nfbc_id is not None:
        drop_player = _find_player(roster, drop_nfbc_id, drop_row_type)
        if drop_player is None:
            return WhatIfResult(
                ok=False,
                message=f"Drop nfbc_id={drop_nfbc_id!r} not found on your roster.",
                add_nfbc_id=add_player.get("nfbc_id"),
                drop_nfbc_id=drop_nfbc_id,
            )
        resolved_drop = _player_key(drop_player)

    suggest_msg = ""
    if resolved_drop is None and auto_suggest_drop:
        resolved_drop, suggest_msg = suggest_drop(
            roster, slot_counts, add_player, **optimize_kwargs
        )
        drop_suggested = resolved_drop is not None
        if resolved_drop is None:
            return WhatIfResult(
                ok=False,
                message=suggest_msg,
                add_nfbc_id=add_player.get("nfbc_id"),
            )

    sim = simulate_add_drop_split_week(
        roster,
        slot_counts,
        add=add_player,
        drop_key=resolved_drop,
        **optimize_kwargs,
    )
    baseline = sim["baseline_monday"]
    what_if = sim["whatif_monday"]
    baseline_fri = sim["baseline_friday"]
    what_if_fri = sim["whatif_friday"]
    net_weekly = float(sim["net_weekly_value"])

    cat_deltas, net_overall, any_within = compute_category_deltas(
        sim["baseline_totals"],
        sim["whatif_totals"],
        plan_rows=plan_rows,
    )

    add_id = add_player.get("nfbc_id")
    add_key = _player_key(add_player)
    starts_mon = add_key in what_if.starter_keys()
    starts_fri = add_key in what_if_fri.starter_keys()
    starts_monday_only = starts_mon and not starts_fri
    starts_friday_only = starts_fri and not starts_mon

    bench_only = (
        not starts_mon
        and not starts_fri
        and abs(net_weekly) < 1e-12
        and baseline.starter_keys() == what_if.starter_keys()
        and baseline_fri.starter_keys() == what_if_fri.starter_keys()
    )

    msg = "What-if complete (Mon–Thu lock + Fri–Sun hitter swap)."
    if drop_suggested and suggest_msg:
        msg = f"What-if complete ({suggest_msg})."
    if bench_only:
        msg += " Add lands on the bench both halves — zero immediate starter impact."
    elif starts_monday_only:
        msg += " Add starts Mon–Thu only; weekend lineup uses another bat."
    elif starts_friday_only:
        msg += " Add starts Fri–Sun only; Mon–Thu lineup uses another bat."

    drop_id = resolved_drop[0] if resolved_drop else None
    drop_rt = resolved_drop[1] if resolved_drop else None

    return WhatIfResult(
        ok=True,
        message=msg,
        add_nfbc_id=add_id,
        drop_nfbc_id=drop_id,
        drop_row_type=drop_rt,
        drop_suggested=drop_suggested,
        baseline=baseline,
        what_if=what_if,
        baseline_friday=baseline_fri,
        what_if_friday=what_if_fri,
        net_weekly_value=net_weekly,
        category_deltas=cat_deltas,
        net_overall_pts_estimate=net_overall,
        any_within_noise=any_within,
        bench_only_add=bench_only,
        starts_monday_only=starts_monday_only,
        starts_friday_only=starts_friday_only,
    )


def _tie_threshold_overall_pts(
    plan_rows: Optional[Sequence[Mapping[str, Any]]],
) -> Optional[float]:
    """Smallest clear overall-pts signal across categories (noise × pts/unit)."""
    by_cat = _plan_lookup(plan_rows)
    thresholds: list[float] = []
    for cat, plan in by_cat.items():
        floor = plan.get("noise_floor_raw")
        if floor is None:
            floor = noise_floor_raw(
                tie_cluster_raw_width=plan.get("tie_cluster_raw_width"),
                raw_unit_size=plan.get("raw_unit_size"),
            )
        pts = plan.get("overall_points_per_raw_unit")
        try:
            floor_f = float(floor) if floor is not None else None
            pts_f = float(pts) if pts is not None else None
        except (TypeError, ValueError):
            continue
        if floor_f is None or pts_f is None:
            continue
        thresholds.append(abs(floor_f) * abs(pts_f))
    if not thresholds:
        return None
    return min(thresholds)


def rank_candidates(
    roster: Sequence[Mapping[str, Any]],
    slot_counts: Mapping[str, int],
    candidate_ids: Sequence[Any],
    *,
    free_agents: Optional[Sequence[Mapping[str, Any]]] = None,
    drop_key: Optional[tuple[Any, str]] = None,
    auto_suggest_drop: bool = True,
    rank_mode: str = RANK_MODE_OVERALL,
    plan_rows: Optional[Sequence[Mapping[str, Any]]] = None,
    **optimize_kwargs: Any,
) -> list[dict[str, Any]]:
    """Rank FAAB candidates; collapse sub-noise differences into tie groups.

    ``rank_mode``:
      - ``weekly_value``: generic optimizer net weekly $
      - ``overall_pts``: team-fit estimated overall category points
    """
    fa_pool = list(free_agents or [])
    rows: list[dict[str, Any]] = []
    unmatched: list[str] = []

    for cid in candidate_ids:
        add_player = _find_player(fa_pool, cid)
        if add_player is None:
            unmatched.append(str(cid))
            rows.append(
                {
                    "add_nfbc_id": cid,
                    "ok": False,
                    "message": "unmatched / empty candidate",
                    "projected_stats": "",
                    "net_weekly_value": None,
                    "net_overall_pts_estimate": None,
                    "any_within_noise": None,
                    "drop_nfbc_id": None,
                    "bench_only_add": None,
                    "rank_key": float("-inf"),
                    "tie_group": None,
                    "display_rank": None,
                    "tied": False,
                }
            )
            continue

        result = analyze_add_drop(
            roster,
            slot_counts,
            add=add_player,
            free_agents=fa_pool,
            drop_key=drop_key,
            auto_suggest_drop=auto_suggest_drop,
            plan_rows=plan_rows,
            **optimize_kwargs,
        )
        if not result.ok:
            key = float("-inf")
        elif rank_mode == RANK_MODE_WEEKLY:
            key = float(result.net_weekly_value)
        elif result.net_overall_pts_estimate is not None:
            key = float(result.net_overall_pts_estimate)
        else:
            key = float(result.net_weekly_value)

        rows.append(
            {
                "add_nfbc_id": cid,
                "ok": result.ok,
                "message": result.message,
                "projected_stats": format_projected_stats(add_player),
                "net_weekly_value": result.net_weekly_value if result.ok else None,
                "net_overall_pts_estimate": (
                    result.net_overall_pts_estimate if result.ok else None
                ),
                "any_within_noise": result.any_within_noise if result.ok else None,
                "drop_nfbc_id": result.drop_nfbc_id,
                "bench_only_add": result.bench_only_add if result.ok else None,
                "rank_key": key,
                "tie_group": None,
                "display_rank": None,
                "tied": False,
            }
        )

    # Best-first stable sort.
    rows.sort(key=lambda r: (-r["rank_key"], str(r["add_nfbc_id"])))

    noise = None
    if rank_mode == RANK_MODE_OVERALL:
        noise = _tie_threshold_overall_pts(plan_rows)
    elif rank_mode == RANK_MODE_WEEKLY:
        # Dollar ranking: treat sub-$0.50 as tied (projection noise).
        noise = 0.5

    group = 0
    prev_key: Optional[float] = None
    for r in rows:
        if not r["ok"] or r["rank_key"] == float("-inf"):
            r["tie_group"] = None
            prev_key = None
            continue
        key = float(r["rank_key"])
        if prev_key is None:
            group += 1
        elif noise is not None and abs(prev_key - key) <= noise + 1e-12:
            pass
        else:
            group += 1
        r["tie_group"] = group
        prev_key = key

    seen: dict[int, int] = {}
    next_rank = 1
    group_sizes: dict[int, int] = {}
    for r in rows:
        g = r["tie_group"]
        if g is None:
            continue
        group_sizes[g] = group_sizes.get(g, 0) + 1
        if g not in seen:
            seen[g] = next_rank
            next_rank += 1
        r["display_rank"] = seen[g]

    for r in rows:
        g = r["tie_group"]
        r["tied"] = bool(g is not None and group_sizes.get(g, 0) > 1)

    if unmatched:
        # Attach warning on the first row for callers that check attrs-like keys.
        rows[0]["_unmatched_warning"] = (
            f"{len(unmatched)} candidate(s) unmatched or empty: "
            + ", ".join(unmatched)
        )
    return rows


def format_delta_rows(deltas: Sequence[CategoryDelta]) -> list[dict[str, Any]]:
    """UI-friendly category delta table."""
    out = []
    for d in deltas:
        out.append(
            {
                "category": d.category,
                "baseline": d.baseline,
                "what_if": d.what_if,
                "delta_raw": d.delta_raw,
                "pts_per_unit": d.overall_points_per_raw_unit,
                "delta_overall_pts_est": d.delta_overall_pts_estimate,
                "noise_floor": d.noise_floor_raw,
                "uncertainty": d.uncertainty,
                "is_ratio": d.is_ratio,
            }
        )
    return out


__all__ = [
    "CategoryDelta",
    "WhatIfResult",
    "RANK_MODE_WEEKLY",
    "RANK_MODE_OVERALL",
    "UNCERTAINTY_CLEAR",
    "UNCERTAINTY_UNKNOWN",
    "UNCERTAINTY_WITHIN_NOISE",
    "analyze_add_drop",
    "compute_category_deltas",
    "format_delta_rows",
    "format_projected_stats",
    "rank_candidates",
    "starters_table",
    "suggest_drop",
]
