"""Synthetic coverage for FAAB what-if (#187)."""

from __future__ import annotations

import pytest

from faab_what_if import (
    RANK_MODE_OVERALL,
    RANK_MODE_WEEKLY,
    UNCERTAINTY_CLEAR,
    UNCERTAINTY_WITHIN_NOISE,
    analyze_add_drop,
    compute_category_deltas,
    format_delta_rows,
    rank_candidates,
    starters_table,
)


def hitter(nfbc_id, pos, dollars, **extra):
    player = {
        "nfbc_id": nfbc_id,
        "player_name": f"H{nfbc_id}",
        "row_type": "hitter",
        "pos_raw": ",".join(pos),
        "pos_array": list(pos),
        "dollars": dollars,
        "dollars_monday_thursday": dollars,
    }
    player.update(extra)
    return player


def pitcher(nfbc_id, dollars, **extra):
    player = {
        "nfbc_id": nfbc_id,
        "player_name": f"P{nfbc_id}",
        "row_type": "pitcher",
        "pos_raw": "SP",
        "pos_array": ["SP"],
        "dollars": dollars,
    }
    player.update(extra)
    return player


def plan_row(category, *, pts_per=1.0, noise=1.0, is_ratio=False, unit=1.0):
    return {
        "category": category,
        "is_ratio": is_ratio,
        "higher_is_better": category not in ("ERA", "WHIP"),
        "overall_points_per_raw_unit": pts_per,
        "noise_floor_raw": noise,
        "raw_unit_size": unit,
        "tie_cluster_raw_width": 0.0,
    }


FULL_PLAN = [
    plan_row("R", pts_per=2.0, noise=1.0),
    plan_row("HR", pts_per=5.0, noise=1.0),
    plan_row("RBI", pts_per=2.0, noise=1.0),
    plan_row("SB", pts_per=8.0, noise=1.0),
    plan_row("AVG", pts_per=20.0, noise=0.001, is_ratio=True, unit=0.001),
    plan_row("K", pts_per=1.0, noise=1.0),
    plan_row("W", pts_per=10.0, noise=1.0),
    plan_row("SV", pts_per=15.0, noise=1.0),
    plan_row("ERA", pts_per=10.0, noise=0.01, is_ratio=True, unit=0.01),
    plan_row("WHIP", pts_per=20.0, noise=0.005, is_ratio=True, unit=0.005),
]


# ---------------------------------------------------------------------------
# Acceptance: inspectable lineups + direct upgrade
# ---------------------------------------------------------------------------


def test_direct_upgrade_is_inspectable():
    roster = [
        hitter(1, ["OF"], 10.0, r=2.0, hr=0.0, rbi=2.0, sb=0.0, hits=5.0, ab=20.0),
    ]
    add = hitter(2, ["OF"], 40.0, r=5.0, hr=2.0, rbi=6.0, sb=1.0, hits=8.0, ab=20.0)

    result = analyze_add_drop(
        roster,
        {"OF": 1},
        add=add,
        drop_key=(1, "hitter"),
        auto_suggest_drop=False,
        plan_rows=FULL_PLAN,
    )
    assert result.ok
    assert result.baseline is not None and result.what_if is not None
    assert result.baseline.starter_ids() == {1}
    assert result.what_if.starter_ids() == {2}
    assert result.net_weekly_value == pytest.approx(30.0)

    base_tbl = starters_table(result.baseline)
    what_tbl = starters_table(result.what_if)
    assert base_tbl[0]["nfbc_id"] == 1
    assert what_tbl[0]["nfbc_id"] == 2

    by_cat = {d.category: d for d in result.category_deltas}
    assert by_cat["R"].delta_raw == pytest.approx(3.0)
    assert by_cat["HR"].delta_raw == pytest.approx(2.0)
    assert by_cat["R"].uncertainty == UNCERTAINTY_CLEAR
    assert result.net_overall_pts_estimate is not None
    assert result.net_overall_pts_estimate > 0


def test_bench_only_acquisition_zero_immediate_impact():
    roster = [
        hitter(1, ["OF"], 30.0, r=4.0, hr=1.0, rbi=4.0, sb=1.0, hits=6.0, ab=20.0),
        hitter(2, ["OF"], 20.0, r=2.0, hr=0.0, rbi=2.0, sb=0.0, hits=4.0, ab=20.0),
    ]
    add = hitter(3, ["OF"], 1.0, r=99.0, hr=99.0, rbi=99.0, sb=99.0, hits=99.0, ab=20.0)

    result = analyze_add_drop(
        roster,
        {"OF": 1},
        add=add,
        drop_key=(2, "hitter"),
        auto_suggest_drop=False,
        plan_rows=FULL_PLAN,
    )
    assert result.ok
    assert result.bench_only_add
    assert result.net_weekly_value == pytest.approx(0.0)
    assert result.baseline.starter_ids() == result.what_if.starter_ids() == {1}
    for d in result.category_deltas:
        if d.delta_raw is not None:
            assert d.delta_raw == pytest.approx(0.0)


def test_position_constraint_blocks_higher_value_add():
    roster = [hitter(1, ["C"], 5.0, r=1.0, hr=0.0, rbi=1.0, sb=0.0, hits=2.0, ab=10.0)]
    add = hitter(2, ["OF"], 99.0, r=10.0, hr=5.0, rbi=10.0, sb=5.0, hits=10.0, ab=20.0)

    result = analyze_add_drop(
        roster,
        {"C": 1},
        add=add,
        auto_suggest_drop=False,  # no drop — roster has room conceptually but C-only
        drop_key=None,
        plan_rows=FULL_PLAN,
    )
    # Without a drop, add sits beside the C; still cannot fill C, so starters unchanged.
    assert result.ok
    assert result.what_if.starter_ids() == {1}
    assert result.net_weekly_value == pytest.approx(0.0)


def test_ratio_tradeoff_uses_aggregate_numerators():
    """High-AVG low-counting add displaces a counting bat — AVG up, R down."""
    slugger = hitter(
        1, ["OF"], 20.0, r=6.0, hr=2.0, rbi=6.0, sb=0.0, hits=4.0, ab=24.0  # .167
    )
    contact = hitter(
        2, ["OF"], 18.0, r=2.0, hr=0.0, rbi=1.0, sb=0.0, hits=10.0, ab=20.0  # .500
    )
    # Need a second OF slot holder so drop is meaningful
    filler = hitter(
        3, ["OF"], 5.0, r=1.0, hr=0.0, rbi=1.0, sb=0.0, hits=3.0, ab=15.0
    )

    # Baseline: start slugger + filler (higher $). What-if: drop filler, add contact
    # — contact out-earns filler but may or may not beat slugger.
    # Force: OF:1 only, drop slugger for contact.
    result = analyze_add_drop(
        [slugger],
        {"OF": 1},
        add=contact,
        drop_key=(1, "hitter"),
        auto_suggest_drop=False,
        plan_rows=FULL_PLAN,
    )
    assert result.ok
    assert result.what_if.starter_ids() == {2}

    by_cat = {d.category: d for d in result.category_deltas}
    assert by_cat["R"].delta_raw == pytest.approx(-4.0)
    assert by_cat["AVG"].baseline == pytest.approx(4.0 / 24.0)
    assert by_cat["AVG"].what_if == pytest.approx(10.0 / 20.0)
    assert by_cat["AVG"].delta_raw == pytest.approx(10.0 / 20.0 - 4.0 / 24.0)

    # Confirm engine aggregates match (not mean of player AVGs).
    assert result.what_if.totals["avg"] == pytest.approx(10.0 / 20.0)


def test_unmatched_candidate_warns_clearly():
    roster = [hitter(1, ["OF"], 10.0)]
    result = analyze_add_drop(
        roster,
        {"OF": 1},
        add_nfbc_id=999,
        free_agents=[],
        auto_suggest_drop=False,
        drop_key=(1, "hitter"),
    )
    assert not result.ok
    assert "unmatched" in result.message.lower() or "not found" in result.message.lower()


def test_rank_switches_between_weekly_and_team_fit():
    """High-$ streamer vs lower-$ steal specialist under SB-heavy plan."""
    roster = [
        hitter(1, ["OF"], 15.0, r=3.0, hr=1.0, rbi=3.0, sb=0.0, hits=5.0, ab=20.0),
        hitter(2, ["OF"], 5.0, r=1.0, hr=0.0, rbi=1.0, sb=0.0, hits=2.0, ab=10.0),
    ]
    # Candidate A: big weekly $, no SB
    a = hitter(10, ["OF"], 25.0, r=4.0, hr=2.0, rbi=5.0, sb=0.0, hits=6.0, ab=20.0)
    # Candidate B: lower $, lots of SB (team-fit when SB pts/unit is huge)
    b = hitter(11, ["OF"], 16.0, r=2.0, hr=0.0, rbi=2.0, sb=3.0, hits=5.0, ab=20.0)

    sb_heavy = []
    for r in FULL_PLAN:
        row = dict(r)
        if row["category"] == "SB":
            row["overall_points_per_raw_unit"] = 50.0
        sb_heavy.append(row)

    weekly = rank_candidates(
        roster,
        {"OF": 1},
        [10, 11],
        free_agents=[a, b],
        drop_key=(2, "hitter"),
        auto_suggest_drop=False,
        rank_mode=RANK_MODE_WEEKLY,
        plan_rows=sb_heavy,
    )
    overall = rank_candidates(
        roster,
        {"OF": 1},
        [10, 11],
        free_agents=[a, b],
        drop_key=(2, "hitter"),
        auto_suggest_drop=False,
        rank_mode=RANK_MODE_OVERALL,
        plan_rows=sb_heavy,
    )

    assert weekly[0]["add_nfbc_id"] == 10  # higher net weekly $
    assert overall[0]["add_nfbc_id"] == 11  # SB-driven team fit


def test_candidates_within_noise_are_tied_not_ranked():
    roster = [
        hitter(1, ["OF"], 10.0, r=2.0, hr=0.0, rbi=2.0, sb=0.0, hits=4.0, ab=20.0),
        hitter(2, ["OF"], 1.0, r=0.0, hr=0.0, rbi=0.0, sb=0.0, hits=1.0, ab=10.0),
    ]
    # Counting-only plan so the tie threshold is 1 R × 2 pts = 2 overall pts.
    # A 0.1 R gap (0.2 overall pts) must present as tied, not ranked.
    counting_plan = [
        plan_row("R", pts_per=2.0, noise=1.0),
        plan_row("HR", pts_per=5.0, noise=1.0),
        plan_row("RBI", pts_per=2.0, noise=1.0),
        plan_row("SB", pts_per=8.0, noise=1.0),
    ]
    c1 = hitter(10, ["OF"], 12.0, r=3.0, hr=0.0, rbi=2.0, sb=0.0, hits=5.0, ab=20.0)
    c2 = hitter(11, ["OF"], 12.0, r=3.1, hr=0.0, rbi=2.0, sb=0.0, hits=5.0, ab=20.0)

    ranked = rank_candidates(
        roster,
        {"OF": 1},
        [10, 11],
        free_agents=[c1, c2],
        drop_key=(2, "hitter"),
        auto_suggest_drop=False,
        rank_mode=RANK_MODE_OVERALL,
        plan_rows=counting_plan,
    )
    assert ranked[0]["ok"] and ranked[1]["ok"]
    assert ranked[0]["display_rank"] == ranked[1]["display_rank"] == 1
    assert ranked[0]["tied"] and ranked[1]["tied"]


def test_net_delta_carries_uncertainty_indication():
    baseline = {"r": 5.0, "hr": 1.0, "rbi": 5.0, "sb": 1.0, "hits": 10.0, "ab": 40.0,
                "avg": 0.250, "k": 0.0, "w": 0.0, "sv": 0.0,
                "ip": 0.0, "er": 0.0, "hits_allowed": 0.0, "walks_allowed": 0.0,
                "era": None, "whip": None}
    # +0.2 R is inside a 1.0 noise floor
    what_if = dict(baseline, r=5.2)
    deltas, net, any_within = compute_category_deltas(baseline, what_if, FULL_PLAN)
    by_cat = {d.category: d for d in deltas}
    assert by_cat["R"].uncertainty == UNCERTAINTY_WITHIN_NOISE
    assert by_cat["R"].delta_overall_pts_estimate == pytest.approx(0.4)
    assert any_within

    what_if_big = dict(baseline, r=8.0)
    deltas2, _, _ = compute_category_deltas(baseline, what_if_big, FULL_PLAN)
    assert {d.category: d for d in deltas2}["R"].uncertainty == UNCERTAINTY_CLEAR

    table = format_delta_rows(deltas)
    assert "uncertainty" in table[0]


def test_rank_unmatched_warning():
    roster = [hitter(1, ["OF"], 10.0)]
    ranked = rank_candidates(
        roster,
        {"OF": 1},
        [999],
        free_agents=[],
        auto_suggest_drop=False,
        drop_key=(1, "hitter"),
        rank_mode=RANK_MODE_WEEKLY,
    )
    assert ranked[0]["ok"] is False
    assert "unmatched" in ranked[0]["message"]
    assert "_unmatched_warning" in ranked[0]


def test_auto_suggest_drop_picks_bench():
    roster = [
        hitter(1, ["OF"], 20.0, r=4.0, hits=6.0, ab=20.0),
        hitter(2, ["OF"], 2.0, r=1.0, hits=2.0, ab=10.0),
    ]
    add = hitter(3, ["OF"], 35.0, r=5.0, hits=7.0, ab=20.0)
    result = analyze_add_drop(
        roster, {"OF": 1}, add=add, auto_suggest_drop=True, plan_rows=FULL_PLAN
    )
    assert result.ok
    assert result.drop_suggested
    assert result.drop_nfbc_id == 2
    assert result.what_if.starter_ids() == {3}
