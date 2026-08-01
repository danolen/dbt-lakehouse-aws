"""Synthetic coverage for the v2 expected-lineup engine (#60)."""

from __future__ import annotations

import itertools

import pytest

from lineup_optimizer import (
    SLOT_ELIGIBILITY,
    LineupResult,
    aggregate_totals,
    optimize_lineup,
    optimize_week,
    score_player,
    simulate_add_drop,
)


def hitter(nfbc_id, pos, dollars, **extra):
    player = {
        "nfbc_id": nfbc_id,
        "player_name": f"H{nfbc_id}",
        "row_type": "hitter",
        "pos_raw": ",".join(pos),
        "pos_array": list(pos),
        "dollars": dollars,
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


def brute_force_best(players, slot_counts):
    """Exhaustive max-value assignment, for small fixtures."""
    slots = []
    for slot, count in slot_counts.items():
        slots.extend([slot] * count)

    best = None
    for combo in itertools.permutations(players, len(slots)):
        total = 0.0
        ok = True
        for slot, player in zip(slots, combo):
            tokens = SLOT_ELIGIBILITY[slot]
            if tokens is not None and not any(t in player["pos_array"] for t in tokens):
                ok = False
                break
            total += float(player["dollars"])
        if ok and (best is None or total > best):
            best = total
    return best


# ---------------------------------------------------------------------------
# Acceptance: at least as valuable as greedy
# ---------------------------------------------------------------------------


def test_beats_greedy_on_multi_position_conflict():
    """Greedy fills SS first and strands the only other MI-eligible bat."""
    players = [
        hitter(1, ["SS", "2B"], 30.0),  # greedy takes this at SS
        hitter(2, ["SS"], 25.0),
        hitter(3, ["OF"], 5.0),
    ]
    slot_counts = {"SS": 1, "MI": 1}

    result = optimize_week(players, slot_counts)
    assigned = {a.slot: a.player["nfbc_id"] for a in result.starters}

    assert assigned == {"SS": 2, "MI": 1}
    assert result.total_score == pytest.approx(55.0)
    assert result.total_score >= brute_force_best(players, slot_counts) - 1e-9
    assert not result.unfilled_slots


def test_matches_brute_force_on_dense_fixture():
    players = [
        hitter(1, ["C"], 12.0),
        hitter(2, ["C", "1B"], 18.0),
        hitter(3, ["1B", "3B"], 20.0),
        hitter(4, ["2B", "SS"], 16.0),
        hitter(5, ["SS"], 14.0),
        hitter(6, ["OF"], 22.0),
    ]
    slot_counts = {"C": 1, "1B": 1, "SS": 1, "MI": 1, "CI": 1, "OF": 1}

    result = optimize_week(players, slot_counts)
    assert result.total_score == pytest.approx(brute_force_best(players, slot_counts))


def test_v1_entry_point_still_works():
    players = [hitter(1, ["OF"], 10.0), hitter(2, ["OF"], 8.0)]
    result = optimize_lineup(players, {"OF": 1})
    assert isinstance(result, LineupResult)
    assert result.starter_ids() == {1}
    assert [p["nfbc_id"] for p in result.bench] == [2]


# ---------------------------------------------------------------------------
# Unfilled slots and missing projections
# ---------------------------------------------------------------------------


def test_unfilled_slots_are_explicit():
    players = [hitter(1, ["OF"], 10.0)]
    result = optimize_week(players, {"OF": 2, "C": 1})

    assert sorted(result.unfilled_slots) == ["C", "OF"]
    assert result.starter_ids() == {1}


def test_missing_projection_is_reported():
    players = [hitter(1, ["OF"], 10.0), hitter(2, ["OF"], None)]
    result = optimize_week(players, {"OF": 1})
    assert result.missing_projection_ids == [2]


def test_no_slots_or_no_players_is_safe():
    assert optimize_week([], {"OF": 2}).unfilled_slots == ["OF", "OF"]
    assert optimize_week([hitter(1, ["OF"], 5.0)], {}).starters == []


# ---------------------------------------------------------------------------
# Pitcher selection and the Monday lock
# ---------------------------------------------------------------------------


def test_pitchers_fill_p_slots_and_never_enter_util():
    players = [
        hitter(1, ["OF"], 4.0),
        pitcher(10, 40.0),
        pitcher(11, 30.0),
        pitcher(12, 20.0),
    ]
    result = optimize_week(players, {"UTIL": 1, "P": 2})

    by_slot = {}
    for a in result.starters:
        by_slot.setdefault(a.slot, []).append(a.player["nfbc_id"])

    assert sorted(by_slot["P"]) == [10, 11]
    assert by_slot["UTIL"] == [1]
    assert [p["nfbc_id"] for p in result.bench] == [12]


def test_two_way_player_can_fill_both_roles():
    """Same nfbc_id in both roles is two rows, so identity includes row_type."""
    players = [
        hitter(7, ["OF"], 25.0),
        pitcher(7, 35.0),
    ]
    result = optimize_week(players, {"OF": 1, "P": 1})

    slots = sorted(a.slot for a in result.starters)
    assert slots == ["OF", "P"]
    assert result.total_score == pytest.approx(60.0)


def test_friday_mode_keeps_pitchers_locked_and_uses_weekend_values():
    """Pitchers cannot be moved after Monday; hitters re-optimize on Fri-Sun."""
    monday_pitchers = [pitcher(10, 40.0)]
    players = [
        hitter(1, ["OF"], 30.0, dollars_friday_sunday=2.0),
        hitter(2, ["OF"], 10.0, dollars_friday_sunday=25.0),
        pitcher(11, 99.0),  # would out-earn the locked arm, must be ignored
    ]

    monday = optimize_week(players, {"OF": 1, "P": 1})
    assert monday.starter_keys() == {(1, "hitter"), (11, "pitcher")}

    friday = optimize_week(
        players,
        {"OF": 1, "P": 1},
        mode="friday",
        locked_pitchers=monday_pitchers,
    )

    starters = {a.slot: a.player["nfbc_id"] for a in friday.starters}
    assert starters["OF"] == 2  # weekend value flips the hitter
    assert starters["P"] == 10  # Monday lock carried through
    assert all(p["row_type"] == "hitter" for p in friday.bench)


def test_friday_injury_swaps_in_the_next_best_bat():
    healthy = [
        hitter(1, ["OF"], 30.0, dollars_friday_sunday=28.0),
        hitter(2, ["OF"], 10.0, dollars_friday_sunday=9.0),
    ]
    assert optimize_week(healthy, {"OF": 1}, mode="friday").starter_ids() == {1}

    # Player 1 goes down Friday: zero out the weekend projection.
    injured = [dict(healthy[0], dollars_friday_sunday=0.0), healthy[1]]
    result = optimize_week(injured, {"OF": 1}, mode="friday")
    assert result.starter_ids() == {2}


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        optimize_week([], {}, mode="tuesday")


# ---------------------------------------------------------------------------
# Category weighting
# ---------------------------------------------------------------------------


def test_category_weights_flip_the_choice_toward_steals():
    """Mirrors the real week-19 call: HR are cheap, SB are expensive."""
    slugger = hitter(1, ["2B"], 20.0, r=4.0, hr=2.0, rbi=5.0, sb=0.0, hits=6.0, ab=24.0)
    speedster = hitter(2, ["2B"], 12.0, r=3.0, hr=0.0, rbi=2.0, sb=2.0, hits=6.0, ab=24.0)
    players = [slugger, speedster]

    neutral = optimize_week(players, {"2B": 1})
    assert neutral.starter_ids() == {1}

    weights = {"r": 2.5, "hr": 1.0, "rbi": 0.5, "sb": 18.0, "avg": 22.5}
    ratio_context = {"hits": 1406.0, "at_bats": 5326.0}
    weighted = optimize_week(
        players, {"2B": 1}, weights=weights, ratio_context=ratio_context
    )
    assert weighted.starter_ids() == {2}


def test_ratio_weighting_prefers_the_better_era():
    good = pitcher(10, 10.0, k=6.0, w=0.5, sv=0.0, ip=6.0, er=1.0, hits_allowed=4.0, walks_allowed=1.0)
    bad = pitcher(11, 10.0, k=6.0, w=0.5, sv=0.0, ip=6.0, er=5.0, hits_allowed=9.0, walks_allowed=4.0)
    weights = {"k": 9.5, "w": 54.0, "sv": 58.0, "era": 13.5, "whip": 28.0}
    ctx = {"earned_runs": 380.0, "innings_pitched": 993.0, "walks_hits_allowed": 1140.0}

    result = optimize_week([good, bad], {"P": 1}, weights=weights, ratio_context=ctx)
    assert result.starter_ids() == {10}


def test_score_player_handles_missing_ratio_context():
    p = hitter(1, ["OF"], 5.0, r=1.0, ab=10.0, hits=3.0)
    assert score_player(p, weights={"avg": 22.5}) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Aggregates
# ---------------------------------------------------------------------------


def test_ratio_aggregates_use_numerators_not_player_averages():
    """A .500 hitter in 2 AB and a .200 hitter in 20 AB is not .350."""
    players = [
        hitter(1, ["OF"], 5.0, hits=1.0, ab=2.0, r=1.0, hr=0.0, rbi=1.0, sb=0.0),
        hitter(2, ["OF"], 4.0, hits=4.0, ab=20.0, r=2.0, hr=1.0, rbi=3.0, sb=1.0),
        pitcher(10, 9.0, k=10.0, w=1.0, sv=0.0, ip=6.0, er=2.0, hits_allowed=5.0, walks_allowed=1.0),
        pitcher(11, 8.0, k=4.0, w=0.0, sv=1.0, ip=2.0, er=2.0, hits_allowed=3.0, walks_allowed=1.0),
    ]
    result = optimize_week(players, {"OF": 2, "P": 2})
    totals = result.totals

    assert totals["hits"] == pytest.approx(5.0)
    assert totals["ab"] == pytest.approx(22.0)
    assert totals["avg"] == pytest.approx(5.0 / 22.0)
    assert totals["avg"] != pytest.approx((0.5 + 0.2) / 2)

    assert totals["ip"] == pytest.approx(8.0)
    assert totals["era"] == pytest.approx(4.0 * 9.0 / 8.0)
    assert totals["whip"] == pytest.approx((8.0 + 2.0) / 8.0)
    assert totals["k"] == pytest.approx(14.0)
    assert totals["sv"] == pytest.approx(1.0)


def test_aggregate_totals_are_none_without_volume():
    totals = aggregate_totals([])
    assert totals["avg"] is None
    assert totals["era"] is None
    assert totals["whip"] is None


def test_totals_exclude_bench():
    players = [
        hitter(1, ["OF"], 50.0, hits=5.0, ab=10.0),
        hitter(2, ["OF"], 1.0, hits=99.0, ab=99.0),
    ]
    result = optimize_week(players, {"OF": 1})
    assert result.totals["ab"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Add/drop what-if
# ---------------------------------------------------------------------------


def test_bench_only_acquisition_has_no_lineup_impact():
    roster = [hitter(1, ["OF"], 30.0), hitter(2, ["OF"], 20.0)]
    add = hitter(3, ["OF"], 1.0)

    baseline, what_if = simulate_add_drop(
        roster, {"OF": 1}, add=add, drop_key=(2, "hitter")
    )
    assert baseline.starter_ids() == what_if.starter_ids() == {1}
    assert baseline.totals == what_if.totals


def test_direct_upgrade_changes_the_lineup():
    roster = [hitter(1, ["OF"], 10.0)]
    add = hitter(2, ["OF"], 40.0)

    baseline, what_if = simulate_add_drop(
        roster, {"OF": 1}, add=add, drop_key=(1, "hitter")
    )
    assert baseline.starter_ids() == {1}
    assert what_if.starter_ids() == {2}
    assert what_if.total_score > baseline.total_score


def test_position_constraint_blocks_a_higher_value_add():
    """A big bat that cannot fill the open slot adds nothing."""
    roster = [hitter(1, ["C"], 5.0)]
    add = hitter(2, ["OF"], 99.0)

    baseline, what_if = simulate_add_drop(roster, {"C": 1}, add=add)
    assert baseline.starter_ids() == {1}
    assert what_if.starter_ids() == {1}
    assert what_if.total_score == pytest.approx(baseline.total_score)


# ---------------------------------------------------------------------------
# Utility Advantage + determinism
# ---------------------------------------------------------------------------


def test_utility_advantage_saves_the_flexible_bat_for_flex_slots():
    """Equal value: spend the single-position bat on the exact slot."""
    players = [
        hitter(1, ["1B", "3B", "OF"], 10.0),
        hitter(2, ["1B"], 10.0),
    ]
    result = optimize_week(players, {"1B": 1, "UTIL": 1})
    assigned = {a.slot: a.player["nfbc_id"] for a in result.starters}

    assert assigned["1B"] == 2
    assert assigned["UTIL"] == 1


def test_utility_advantage_never_overrides_real_value():
    players = [
        hitter(1, ["1B", "3B", "OF"], 10.0),
        hitter(2, ["1B"], 1.0),
    ]
    result = optimize_week(players, {"1B": 1})
    assert result.starter_ids() == {1}
    assert result.total_score == pytest.approx(10.0)


def test_deterministic_under_ties():
    players = [hitter(i, ["OF"], 10.0) for i in range(1, 6)]
    runs = {
        tuple(sorted(optimize_week(players, {"OF": 2}).starter_ids()))
        for _ in range(20)
    }
    assert len(runs) == 1


def test_runtime_is_interactive_for_a_full_roster():
    import time

    players = [
        hitter(i, ["OF", "1B"] if i % 3 else ["C"], float(60 - i)) for i in range(1, 41)
    ]
    players += [pitcher(100 + i, float(50 - i)) for i in range(20)]
    slot_counts = {
        "C": 2, "1B": 1, "2B": 1, "3B": 1, "SS": 1,
        "MI": 1, "CI": 1, "OF": 5, "UTIL": 1, "P": 9,
    }

    start = time.perf_counter()
    optimize_week(players, slot_counts)
    assert time.perf_counter() - start < 1.0
