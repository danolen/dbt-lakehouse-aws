"""
Fantasy Baseball In-Season Tool

FAAB worksheet + weekly lineup optimizer for NFBC league management.
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor

from lineup_optimizer import optimize_week

# Display order for the starters table. Intentionally different from the
# greedy fill order (which is most-constrained first) — this is purely a
# UX preference for reading the lineup left-to-right the way it shows up
# on the NFBC roster page.
SLOT_DISPLAY_ORDER = ["C", "1B", "2B", "SS", "3B", "MI", "CI", "OF", "UTIL"]

load_dotenv()

st.set_page_config(
    page_title="In-Season Tool",
    page_icon="⚾",
    layout="wide",
)


def get_config(key, default=None):
    try:
        if "default" in st.secrets and key in st.secrets["default"]:
            return st.secrets["default"][key]
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.getenv(key, default)


ATHENA_SCHEMA = get_config("ATHENA_SCHEMA", "dbt_main")
# dbt_project.yml sends main/stage/source models to schema `dbt_<name>`, but
# seeds have no +schema override so they land in the base profile schema
# (e.g. `dbt`). Override via env/secret if that changes.
ATHENA_SEEDS_SCHEMA = get_config("ATHENA_SEEDS_SCHEMA", "dbt")
ATHENA_REGION = get_config("ATHENA_REGION", "us-east-1")
ATHENA_S3_OUTPUT = get_config("ATHENA_S3_OUTPUT")

for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION"):
    val = get_config(key, ATHENA_REGION if key == "AWS_DEFAULT_REGION" else None)
    if val and not os.getenv(key):
        os.environ[key] = val

if not ATHENA_S3_OUTPUT:
    st.error(
        "**Configuration Error:** `ATHENA_S3_OUTPUT` is required.\n\n"
        "Create a `.env` file with: `ATHENA_S3_OUTPUT=s3://your-bucket/query-results/`"
    )
    st.stop()


LEAGUES = {
    "OC": "nolen_oc",
    "Cash 12": "nolen_cash_12",
    "OCQ": "nolen_ocq",
    "Cash 15": "nolen_cash_15",
    "NFBC 50": "nolen_50",
}


def _optimize_df(df):
    for col in df.select_dtypes(include=["object"]).columns:
        if df[col].nunique() / max(len(df), 1) < 0.5:
            df[col] = df[col].astype("category")
    for col in df.select_dtypes(include=["int64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="integer")
    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")
    return df


def _connect():
    return connect(
        s3_staging_dir=ATHENA_S3_OUTPUT,
        region_name=ATHENA_REGION,
        schema_name=ATHENA_SCHEMA,
        cursor_class=PandasCursor,
    )


@st.cache_data(ttl=900)
def load_faab_data(league):
    query = f"""
        SELECT * FROM {ATHENA_SCHEMA}.mart_faab_worksheet
        WHERE league = '{league}'
    """
    return _optimize_df(_connect().cursor().execute(query).as_pandas())


@st.cache_data(ttl=900)
def load_unmatched():
    query = f"SELECT * FROM {ATHENA_SCHEMA}.mart_faab_unmatched"
    return _connect().cursor().execute(query).as_pandas()


@st.cache_data(ttl=900)
def load_lineup_inputs(league):
    query = f"""
        SELECT * FROM {ATHENA_SCHEMA}.mart_weekly_lineup_inputs
        WHERE league = '{league}'
    """
    return _connect().cursor().execute(query).as_pandas()


@st.cache_data(ttl=3600)
def load_roster_slots():
    query = f"SELECT * FROM {ATHENA_SEEDS_SCHEMA}.league_roster_slots"
    return _connect().cursor().execute(query).as_pandas()


try:
    unmatched_df = load_unmatched()
except Exception:
    unmatched_df = pd.DataFrame()

unmatched_count = len(unmatched_df)

st.title("⚾ In-Season Tool")
if unmatched_count > 0:
    if st.button(
        f"🟡 {unmatched_count} unmatched FTN players",
        key="unmatched_ftn_badge",
        type="tertiary",
    ):
        st.session_state["open_unmatched_expander"] = True
        st.toast("Open the FAAB Worksheet tab to review unmatched players.")

st.sidebar.header("League")
selected_league = st.sidebar.selectbox("Select League", list(LEAGUES.keys()))
league_key = LEAGUES[selected_league]


tab_faab, tab_lineup = st.tabs(["FAAB Worksheet", "Lineup Optimizer"])


# ---------------------------------------------------------------------------
# FAAB Worksheet tab
# ---------------------------------------------------------------------------

with tab_faab:
    st.sidebar.header("FAAB Filters")
    ftn_only = st.sidebar.checkbox("FTN recommended only", value=False)

    try:
        df = load_faab_data(league_key)
    except Exception as e:
        st.error(f"Failed to load data from Athena: {e}")
        st.stop()

    # League-level FAAB budget (full table, not sidebar filters) for help UI.
    league_has_faab = (
        "my_faab_remaining" in df.columns
        and df["my_faab_remaining"].notna().any()
        and (
            pd.to_numeric(df["my_faab_remaining"], errors="coerce").fillna(0) > 0
        ).any()
    )

    if league_key == "nolen_50":
        st.info(
            "NFBC 50 is draft-and-hold — no FAAB. This tab still shows weekly "
            "projection data for rostered players; use the Lineup Optimizer tab "
            "for start/sit."
        )

    all_positions = sorted(
        {
            p.strip()
            for pos in df["position"].dropna().unique()
            for p in str(pos).split(",")
        }
    )
    selected_positions = st.sidebar.multiselect(
        "Position", all_positions, default=all_positions
    )

    all_types = sorted(
        df.loc[df["has_ftn_rec"] == 1, "ftn_type"].dropna().unique().tolist()
    )
    selected_types = st.sidebar.multiselect("FTN Type", all_types, default=all_types)

    FREE_AGENT = "Free Agent"
    owner_values = sorted(df["owner"].dropna().loc[df["owner"] != ""].unique().tolist())
    owner_options = [FREE_AGENT] + owner_values
    selected_owners = st.sidebar.multiselect(
        "Owner", owner_options, default=[FREE_AGENT]
    )

    search = st.sidebar.text_input("Search player")

    mask = pd.Series(True, index=df.index)

    if ftn_only:
        mask &= df["has_ftn_rec"] == 1

    if selected_positions:
        pos_pattern = "|".join(selected_positions)
        mask &= df["position"].str.contains(pos_pattern, na=False)

    if selected_types and ftn_only:
        mask &= df["ftn_type"].isin(selected_types)

    if selected_owners:
        is_free_agent = df["owner"].isna() | (df["owner"] == "")
        is_selected_owner = df["owner"].isin(
            [o for o in selected_owners if o != FREE_AGENT]
        )
        mask &= (
            is_free_agent if FREE_AGENT in selected_owners else False
        ) | is_selected_owner

    if search:
        mask &= df["player"].str.contains(search, case=False, na=False)

    display = df.loc[mask].copy()

    has_faab = (
        "my_faab_remaining" in display.columns
        and display["my_faab_remaining"].notna().any()
        and (pd.to_numeric(display["my_faab_remaining"], errors="coerce").fillna(0) > 0).any()
    )

    def _format_pct_of_faab(v):
        # Emoji prefix preserved in the rendered string; the underlying
        # sort uses the raw numeric column so "🔴 17.9%" still sorts above
        # "🟢 4.0%". Thresholds per Phase 1b plan: <5% green, 5-15% yellow,
        # >15% red.
        if v is None or pd.isna(v):
            return ""
        if v < 5:
            badge = "🟢"
        elif v < 15:
            badge = "🟡"
        else:
            badge = "🔴"
        return f"{badge} {v:.1f}%"

    if has_faab:
        display["pct_of_budget_display"] = display["high_bid_pct_of_faab"].apply(
            _format_pct_of_faab
        )
    else:
        display["pct_of_budget_display"] = ""

    # FTN status arrows live in `status_tag` (e.g. "⬆️", "⬇️"). Prefix the
    # player name when set so trending adds are scannable at a glance.
    def _prefix_arrow(row):
        name = row.get("player")
        tag = row.get("status_tag")
        if not isinstance(name, str):
            return name
        if not isinstance(tag, str) or not tag.strip():
            return name
        if tag in name:
            return name
        return f"{tag} {name}"

    display["player"] = display.apply(_prefix_arrow, axis=1)

    COLUMNS = {
        "player": "Player",
        "position": "Pos",
        "team": "Team",
        "ftn_type": "Type",
        "low_bid": "Low $",
        "high_bid": "High $",
        "pct_of_budget_display": "% of Budget",
        "ros_value": "RoS $",
        "rfs12": "RFS12",
        "rfs15": "RFS15",
        "dollars": "Wk $",
        "dollars_per_game": "Wk $/G",
        "dollars_monday_thursday": "M-Th $",
        "dollars_friday_sunday": "F-Su $",
        "owner": "Owner",
        "own_pct": "Own%",
        "ftn_notes": "Notes",
    }

    # Hide FAAB-specific columns for draft-and-hold leagues (nolen_50 with
    # my_faab_remaining = 0). Everything else stays since projection/ROS
    # data is still useful for trade/drop decisions there.
    if not has_faab:
        COLUMNS.pop("pct_of_budget_display", None)

    sort_cols = [
        c for c in ["has_ftn_rec", "high_bid", "ros_value"] if c in display.columns
    ]
    if sort_cols:
        display = display.sort_values(
            sort_cols, ascending=[False] * len(sort_cols), na_position="last"
        )

    visible = {k: v for k, v in COLUMNS.items() if k in display.columns}
    out = display[[c for c in visible if c in display.columns]].copy()

    for col in (
        "ros_value",
        "dollars",
        "dollars_per_game",
        "dollars_monday_thursday",
        "dollars_friday_sunday",
    ):
        if col in out.columns:
            out[col] = out[col].round(1)

    out = out.rename(columns=visible)

    st.subheader(f"FAAB Worksheet — {selected_league}")

    if league_has_faab:
        with st.expander("Cross-league-size FTN recs (manual)", expanded=False):
            st.markdown(
                "FTN publishes separate 12- and 15-team FAAB files. A player can "
                "appear in one file and not the other. This table only shows the "
                "recommendation for **your** league’s FTN file size. "
                "If you are comparing to the **other** file, translate the low/high "
                "range using the role heuristics below (by FTN **Type**, not raw "
                "position). Round to a sensible whole-dollar bid."
            )
            st.markdown(
                "| Direction | Rule of thumb |\n"
                "|-----------|---------------|\n"
                "| **12T → 15T** (player only in the 12-team file) | Apply the "
                "multiplier to the **midpoint** of Low/High: **1.3×** default; "
                "**1.5×** closer / saves-chase specs; **1.4×** non-closer "
                "high-leverage RP; **1.25×** SP streamers. |\n"
                "| **15T → 12T** (player only in the 15-team file) | Divide the "
                "midpoint by the **same** factor (15-team pools are shallower; "
                "the name often clears for less). |\n"
            )
            st.caption(
                "Example: 12T Low/High 80–160 on a closer-type add — midpoint 120; "
                "for 15T context try ~1.5× → **~180** (illustrative only)."
            )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Players", len(out))
    c2.metric("FTN Recs", int((display["has_ftn_rec"] == 1).sum()))
    week_val = (
        display["week_of"].dropna().iloc[0]
        if "week_of" in display.columns and not display["week_of"].dropna().empty
        else "N/A"
    )
    c3.metric("Week Of", week_val)
    if has_faab:
        faab_val = pd.to_numeric(
            display["my_faab_remaining"], errors="coerce"
        ).dropna()
        faab_as_of = (
            display["faab_as_of_date"].dropna().iloc[0]
            if "faab_as_of_date" in display.columns
               and not display["faab_as_of_date"].dropna().empty
            else None
        )
        c4.metric(
            "Your FAAB",
            f"${int(faab_val.iloc[0])}" if not faab_val.empty else "N/A",
            help=(
                f"As of {faab_as_of}. Update `dbt/seeds/faab_remaining.csv` "
                "and re-seed weekly."
            ) if faab_as_of else None,
        )
    else:
        unowned_count = (
            len(display[display["owner"].isna() | (display["owner"] == "")])
            if "owner" in display.columns
            else "—"
        )
        c4.metric("Unowned", unowned_count)

    st.dataframe(out, use_container_width=True, hide_index=True, height=700)

    if unmatched_count > 0:
        with st.expander(
            f"🟡 {unmatched_count} unmatched FTN players",
            expanded=st.session_state.get("open_unmatched_expander", False),
        ):
            st.markdown(
                "These FTN players could not be matched to an NFBC ID. "
                "Add overrides to `dbt/seeds/ftn_nfbc_player_overrides.csv` "
                "then run `dbt seed && dbt build`."
            )
            st.dataframe(unmatched_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Lineup Optimizer tab (Phase 1a v1: greedy, Monday-lock, hitters only)
# ---------------------------------------------------------------------------

with tab_lineup:
    st.subheader(f"Weekly Lineup Optimizer — {selected_league}")

    try:
        lineup_df = load_lineup_inputs(league_key)
        slots_df = load_roster_slots()
    except Exception as e:
        st.error(f"Failed to load lineup data: {e}")
        st.stop()

    if lineup_df.empty:
        st.warning(
            f"No rows in `mart_weekly_lineup_inputs` for league `{league_key}`. "
            "Confirm the in-season-players CSV is uploaded to S3 for today's "
            "partition and `dbt build` has run."
        )
        st.stop()

    owner_options = sorted(
        lineup_df["owner"].dropna().loc[lineup_df["owner"] != ""].unique().tolist()
    )
    if not owner_options:
        st.warning("No owners found in the lineup inputs mart.")
        st.stop()

    selected_owner = st.selectbox(
        "Owner (team to optimize)",
        owner_options,
        key="lineup_owner",
    )

    fmt = lineup_df["format"].dropna().iloc[0]
    week_of = (
        lineup_df["week_of"].dropna().iloc[0]
        if "week_of" in lineup_df.columns and not lineup_df["week_of"].dropna().empty
        else "N/A"
    )

    def _slot_counts_for(group):
        rows = slots_df[
            (slots_df["format"] == fmt) & (slots_df["slot_group"] == group)
        ]
        return dict(
            zip(
                rows["slot"].astype(str).tolist(),
                rows["count"].astype(int).tolist(),
            )
        )

    hitter_slot_counts = _slot_counts_for("hitter")
    pitcher_slot_counts = _slot_counts_for("pitcher")

    if not hitter_slot_counts:
        st.error(
            f"No hitter slot config found for format `{fmt}` in "
            "`league_roster_slots`. Re-run `dbt seed`."
        )
        st.stop()

    # NFBC locks pitchers for the full week on Monday and allows hitter-only
    # swaps on Friday, so the two windows are different questions.
    lineup_mode = st.radio(
        "Lineup window",
        options=["monday", "friday"],
        format_func=lambda m: (
            "Monday lock (Mon–Thu hitters + week pitchers)"
            if m == "monday"
            else "Friday swap (hitters only, Fri–Sun)"
        ),
        horizontal=True,
        key="lineup_mode",
    )

    slot_counts = dict(hitter_slot_counts)
    if lineup_mode == "monday":
        slot_counts.update(pitcher_slot_counts)

    team_all = lineup_df[lineup_df["owner"] == selected_owner].copy()

    if team_all.empty:
        st.warning(f"No players rostered to `{selected_owner}`.")
        st.stop()

    if "row_type" not in team_all.columns:
        team_all["row_type"] = "hitter"
    team_all["row_type"] = team_all["row_type"].fillna("hitter")

    # Derive pos_array from pos_raw (plain comma-separated string) rather
    # than trusting the Athena array column — pyathena serializes arrays as
    # strings like "[C, 1B]" which breaks naive comma splits.
    def _parse_pos(raw):
        if raw is None:
            return []
        return [p.strip().upper() for p in str(raw).split(",") if p.strip()]

    team_all["pos_array"] = team_all["pos_raw"].apply(_parse_pos)

    team = team_all[team_all["row_type"] == "hitter"].copy()
    team_pitchers = team_all[team_all["row_type"] == "pitcher"].copy()

    if team.empty:
        st.warning(
            f"No hitter rows rostered to `{selected_owner}` with a weekly "
            "hitting projection."
        )
        st.stop()

    players = team_all.to_dict(orient="records")

    if lineup_mode == "friday":
        # Pitchers were locked Monday; carry the Monday set through untouched.
        monday = optimize_week(
            players, {**hitter_slot_counts, **pitcher_slot_counts}, mode="monday"
        )
        locked_pitchers = [
            a.player for a in monday.starters if a.slot == "P"
        ]
        result = optimize_week(
            players,
            slot_counts,
            mode="friday",
            locked_pitchers=locked_pitchers,
        )
    else:
        result = optimize_week(players, slot_counts, mode="monday")

    active_capacity = sum(slot_counts.values())
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Week Of", str(week_of))
    c2.metric("Team Hitters", len(team))
    c3.metric("Active Slots", active_capacity)
    c4.metric("Projected $", f"{result.total_score:.1f}")

    # Monday lock scores/displays Mon–Thu hitter components when present (#210).
    use_mt = lineup_mode == "monday"
    if lineup_mode == "monday":
        dollar_field, dollar_label = "dollars_monday_thursday", "M-Th $"
    elif lineup_mode == "friday":
        dollar_field, dollar_label = "dollars_friday_sunday", "F-Su $"
    else:
        dollar_field, dollar_label = "dollars", "Wk $"

    def _num(value):
        try:
            if value is None or (isinstance(value, float) and value != value):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _hitter_stat(player, key):
        """Prefer Mon–Thu ``mt_*`` fields on Monday; else full-week components."""
        if use_mt:
            mt_key = {
                "r": "mt_r",
                "hr": "mt_hr",
                "rbi": "mt_rbi",
                "sb": "mt_sb",
                "hits": "mt_hits",
                "ab": "mt_ab",
                "num_g": "mt_num_g",
                "home_games": "mt_home_games",
                "away_games": "mt_away_games",
                "vs_rhp": "mt_vs_rhp",
                "vs_lhp": "mt_vs_lhp",
                "batting_avg": "mt_batting_avg",
            }.get(key)
            if mt_key is not None:
                mt_val = _num(player.get(mt_key))
                if mt_val is not None:
                    return mt_val
        return _num(player.get(key))

    def _fmt(value, spec):
        return format(value, spec) if isinstance(value, (int, float)) else "—"

    # Expected totals from starters only — two cross-tabs (hitting / pitching).
    hit_r = hit_hr = hit_rbi = hit_sb = hit_h = hit_ab = 0.0
    pit_k = pit_w = pit_sv = pit_ip = pit_er = pit_h = pit_bb = 0.0
    for a in result.starters:
        p = a.player
        if a.slot == "P" or (p.get("row_type") or "hitter") == "pitcher":
            pit_k += _num(p.get("k")) or 0.0
            pit_w += _num(p.get("w")) or 0.0
            pit_sv += _num(p.get("sv")) or 0.0
            pit_ip += _num(p.get("ip")) or 0.0
            pit_er += _num(p.get("er")) or 0.0
            pit_h += _num(p.get("hits_allowed")) or 0.0
            pit_bb += _num(p.get("walks_allowed")) or 0.0
        else:
            hit_r += _hitter_stat(p, "r") or 0.0
            hit_hr += _hitter_stat(p, "hr") or 0.0
            hit_rbi += _hitter_stat(p, "rbi") or 0.0
            hit_sb += _hitter_stat(p, "sb") or 0.0
            hit_h += _hitter_stat(p, "hits") or 0.0
            hit_ab += _hitter_stat(p, "ab") or 0.0

    hit_avg = (hit_h / hit_ab) if hit_ab > 0 else None
    pit_era = ((pit_er * 9.0) / pit_ip) if pit_ip > 0 else None
    pit_whip = ((pit_h + pit_bb) / pit_ip) if pit_ip > 0 else None

    window_note = (
        "Mon–Thu hitter projections"
        if use_mt
        else ("Fri–Sun hitter $" if lineup_mode == "friday" else "full-week projections")
    )
    st.markdown("### Expected lineup totals")
    st.caption(
        f"Starters only ({window_note}). Ratios use summed numerators/"
        "denominators (H÷AB, ER×9÷IP, (H+BB)÷IP), not averaged player rates."
    )
    hit_col, pit_col = st.columns(2)
    with hit_col:
        st.markdown("**Hitting**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "R": _fmt(hit_r, ".1f"),
                        "HR": _fmt(hit_hr, ".1f"),
                        "RBI": _fmt(hit_rbi, ".1f"),
                        "SB": _fmt(hit_sb, ".1f"),
                        "H": _fmt(hit_h, ".1f"),
                        "AB": _fmt(hit_ab, ".1f"),
                        "AVG": _fmt(hit_avg, ".3f"),
                    }
                ],
                index=["Projected"],
            ),
            use_container_width=True,
        )
    with pit_col:
        st.markdown("**Pitching**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "K": _fmt(pit_k, ".1f"),
                        "W": _fmt(pit_w, ".1f"),
                        "SV": _fmt(pit_sv, ".1f"),
                        "IP": _fmt(pit_ip, ".1f"),
                        "ER": _fmt(pit_er, ".1f"),
                        "H": _fmt(pit_h, ".1f"),
                        "BB": _fmt(pit_bb, ".1f"),
                        "ERA": _fmt(pit_era, ".2f"),
                        "WHIP": _fmt(pit_whip, ".2f"),
                    }
                ],
                index=["Projected"],
            ),
            use_container_width=True,
        )

    if result.missing_projection_ids:
        st.info(
            f"{len(result.missing_projection_ids)} rostered player(s) have no "
            "weekly projection for this window and were scored as zero."
        )

    if result.unfilled_slots:
        st.warning(
            "Unfilled slots (not enough eligible hitters): "
            + ", ".join(result.unfilled_slots)
        )

    HITTER_COLS = [
        "slot",
        "player_name",
        "team",
        "pos_raw",
        "bats",
        "num_g",
        "dollars",
        "r",
        "hr",
        "rbi",
        "sb",
        "hits",
        "ab",
        "batting_avg",
        "home_games",
        "away_games",
        "vs_rhp",
        "vs_lhp",
        "ros_value",
    ]
    HITTER_LABELS = {
        "slot": "Slot",
        "player_name": "Player",
        "team": "Team",
        "pos_raw": "Pos",
        "bats": "B",
        "num_g": "G",
        "dollars": dollar_label,
        "r": "R",
        "hr": "HR",
        "rbi": "RBI",
        "sb": "SB",
        "hits": "H",
        "ab": "AB",
        "batting_avg": "AVG",
        "home_games": "HG",
        "away_games": "AG",
        "vs_rhp": "vR",
        "vs_lhp": "vL",
        "ros_value": "RoS $",
    }

    def _hitter_row(player, *, slot=None):
        row = {}
        if slot is not None:
            row["slot"] = slot
        row["player_name"] = player.get("player_name")
        row["team"] = player.get("team")
        row["pos_raw"] = player.get("pos_raw")
        row["bats"] = player.get("bats")
        row["num_g"] = _hitter_stat(player, "num_g")
        dollar_val = _num(player.get(dollar_field))
        if dollar_val is None:
            dollar_val = _num(player.get("dollars"))
        row["dollars"] = dollar_val
        for key in ("r", "hr", "rbi", "sb", "hits", "ab", "batting_avg"):
            row[key] = _hitter_stat(player, key)
        if row["batting_avg"] is None and row["ab"]:
            hits = row["hits"] or 0.0
            row["batting_avg"] = hits / row["ab"] if row["ab"] else None
        row["home_games"] = _hitter_stat(player, "home_games")
        row["away_games"] = _hitter_stat(player, "away_games")
        row["vs_rhp"] = _hitter_stat(player, "vs_rhp")
        row["vs_lhp"] = _hitter_stat(player, "vs_lhp")
        row["ros_value"] = _num(player.get("ros_value"))
        return row

    def _hitter_frame(records, *, include_slot=False):
        cols = HITTER_COLS if include_slot else [c for c in HITTER_COLS if c != "slot"]
        df_h = pd.DataFrame(records, columns=cols)
        for col in cols:
            if col in ("slot", "player_name", "team", "pos_raw", "bats"):
                continue
            decimals = 3 if col == "batting_avg" else (1 if col in ("dollars", "ros_value", "sb", "r", "hr", "rbi", "hits", "ab") else 1)
            df_h[col] = pd.to_numeric(df_h[col], errors="coerce").round(decimals)
        return df_h

    starters_records = []
    slot_order_index = {s: i for i, s in enumerate(SLOT_DISPLAY_ORDER)}
    for a in result.starters:
        if a.slot == "P":
            continue
        starters_records.append(_hitter_row(a.player, slot=a.slot))

    starters_df = _hitter_frame(starters_records, include_slot=True)
    if not starters_df.empty:
        starters_df["_slot_order"] = starters_df["slot"].map(slot_order_index).fillna(99)
        starters_df = (
            starters_df.sort_values(["_slot_order", "dollars"], ascending=[True, False])
            .drop(columns=["_slot_order"])
            .reset_index(drop=True)
        )

    st.markdown("### Starters")
    st.dataframe(
        starters_df.rename(columns=HITTER_LABELS),
        use_container_width=True,
        hide_index=True,
    )

    bench_hitters = [
        p for p in result.bench if (p.get("row_type") or "hitter") == "hitter"
    ]
    bench_pitchers = [p for p in result.bench if p.get("row_type") == "pitcher"]
    bench_records = [_hitter_row(p) for p in bench_hitters]
    bench_df = _hitter_frame(bench_records, include_slot=False)
    if not bench_df.empty:
        bench_df = bench_df.sort_values(
            "dollars", ascending=False, na_position="last"
        ).reset_index(drop=True)

    st.markdown(f"### Bench hitters ({len(bench_df)})")
    st.dataframe(
        bench_df.rename(columns=HITTER_LABELS),
        use_container_width=True,
        hide_index=True,
    )

    PITCHER_COLS = [
        "player_name",
        "team",
        "pos_raw",
        "dollars",
        "pitch_g",
        "gs",
        "first_start_day",
        "is_two_start",
        "opps",
        "w",
        "sv",
        "k",
        "ip",
        "er",
        "hits_allowed",
        "walks_allowed",
        "era",
        "whip",
        "ros_value",
    ]
    PITCHER_LABELS = {
        "player_name": "Player",
        "team": "Team",
        "pos_raw": "Pos",
        "dollars": "Wk $",
        "pitch_g": "G",
        "gs": "GS",
        "first_start_day": "1st",
        "is_two_start": "2-start",
        "opps": "Opp",
        "w": "W",
        "sv": "SV",
        "k": "K",
        "ip": "IP",
        "er": "ER",
        "hits_allowed": "H",
        "walks_allowed": "BB",
        "era": "ERA",
        "whip": "WHIP",
        "ros_value": "RoS $",
    }

    def _pitcher_frame(records):
        df_p = pd.DataFrame(
            [{k: p.get(k) for k in PITCHER_COLS} for p in records],
            columns=PITCHER_COLS,
        )
        for col in PITCHER_COLS:
            if col in ("player_name", "team", "pos_raw", "first_start_day", "opps", "is_two_start"):
                continue
            df_p[col] = pd.to_numeric(df_p[col], errors="coerce").round(2)
        return df_p.sort_values("dollars", ascending=False, na_position="last")

    started_pitchers = [a.player for a in result.starters if a.slot == "P"]

    if started_pitchers:
        st.markdown(f"### Pitchers started ({len(started_pitchers)})")
        if lineup_mode == "friday":
            st.caption(
                "Pitchers locked at Monday's deadline — NFBC does not allow "
                "pitcher changes during the week."
            )
        st.dataframe(
            _pitcher_frame(started_pitchers).rename(columns=PITCHER_LABELS),
            use_container_width=True,
            hide_index=True,
        )

    if bench_pitchers:
        st.markdown(f"### Bench pitchers ({len(bench_pitchers)})")
        st.dataframe(
            _pitcher_frame(bench_pitchers).rename(columns=PITCHER_LABELS),
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("How this works (v2)"):
        st.markdown(
            "- **Exact assignment**: hitters are matched to C/1B/2B/3B/SS/MI/"
            "CI/OF/UTIL with a Hungarian solver, so a player eligible at two "
            "scarce slots can no longer strand a better lineup the way the v1 "
            "greedy fill could.\n"
            "- **Pitchers**: the nine P slots are filled from weekly pitcher "
            "projections in the same pass.\n"
            "- **Monday lock vs Friday swap**: NFBC locks pitchers for the "
            "whole week on Monday and permits hitter-only swaps on Friday. "
            "Monday scores hitters on Mon–Thu dollars (pitchers still use "
            "weekly $). Friday re-optimizes hitters on Fri–Sun projections and "
            "carries the Monday pitcher set through unchanged.\n"
            "- **Expected totals**: hitting and pitching projections from the "
            "active starters only, shown as separate tables. Monday uses "
            "Mon–Thu hitter components when available; pitchers always use "
            "full-week projections. Ratios use summed numerators/denominators "
            "(H/AB, ER/IP, (H+BB)/IP).\n"
            "- **Utility Advantage**: when two hitters are equally valuable, "
            "the less flexible one takes the exact slot so the multi-position "
            "bat stays available for UTIL/MI/CI.\n"
            "- **Next**: category weighting from overall mobility (#186) and "
            "FAAB add/drop what-if (#187) both call this same engine."
        )
