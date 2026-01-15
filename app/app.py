"""
Fantasy Baseball Draft Tool - Streamlit App

Main Streamlit application for draft preparation and tracking.
Optimized for slow drafts (2-4 hour pick clocks, multiple concurrent drafts).
"""

import streamlit as st
import pandas as pd
from datetime import datetime
from app.utils.database import AthenaQuery
from app.utils.dynamodb import DraftTracker, DraftRegistry
from app.config.aws_config import AWSConfig

# Page configuration
st.set_page_config(
    page_title="Fantasy Baseball Draft Tool",
    page_icon="⚾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state
if 'athena_query' not in st.session_state:
    st.session_state.athena_query = AthenaQuery()

if 'draft_registry' not in st.session_state:
    st.session_state.draft_registry = DraftRegistry()

if 'draft_tracker' not in st.session_state:
    st.session_state.draft_session_id = st.session_state.get('draft_session_id', None)
    st.session_state.format_type = st.session_state.get('format_type', '50s')
    if st.session_state.draft_session_id:
        st.session_state.draft_tracker = DraftTracker(
            st.session_state.draft_session_id, 
            st.session_state.format_type
        )
    else:
        st.session_state.draft_tracker = None

if 'player_data' not in st.session_state:
    st.session_state.player_data = None

if 'cache_version' not in st.session_state:
    # Cache version used to force cache refresh after dbt model updates
    st.session_state.cache_version = datetime.now().strftime('%Y%m%d_%H%M%S')


def create_new_draft(format_type: str, description: str, num_teams: int, num_rounds: int, pick_clock: float) -> str:
    """Create a new draft and return draft ID"""
    # Generate draft ID from description or use timestamp
    draft_id = description.lower().replace(' ', '_').replace('/', '_')[:50]
    if not draft_id or draft_id == '_':
        draft_id = f"{format_type}_draft_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Ensure unique ID
    existing = st.session_state.draft_registry.get_draft_metadata(draft_id)
    if existing:
        draft_id = f"{draft_id}_{datetime.now().strftime('%H%M%S')}"
    
    # Register draft
    if st.session_state.draft_registry.register_draft(
        draft_id=draft_id,
        format_type=format_type,
        description=description,
        num_teams=num_teams,
        num_rounds=num_rounds,
        pick_clock_hours=pick_clock
    ):
        return draft_id
    return None


def switch_draft(draft_id: str):
    """Switch to a different draft"""
    metadata = st.session_state.draft_registry.get_draft_metadata(draft_id)
    if metadata:
        st.session_state.draft_session_id = draft_id
        st.session_state.format_type = metadata.get('format_type', '50s')
        st.session_state.draft_tracker = DraftTracker(draft_id, st.session_state.format_type)
        st.session_state.player_data = None  # Clear session state (cache will refresh if expired or version changed)
        st.rerun()


def main():
    """Main application function"""
    
    # Title and header
    st.title("⚾ Fantasy Baseball Draft Tool")
    st.markdown("**Optimized for slow drafts with 2-4 hour pick clocks**")
    st.markdown("---")
    
    # Validate AWS credentials
    is_valid, error_msg = AWSConfig.validate_aws_credentials()
    if not is_valid:
        st.error(f"⚠️ AWS credentials not configured: {error_msg}")
        st.info("""
        **To configure AWS credentials:**
        1. Run `aws configure` in your terminal, OR
        2. Set environment variables:
           - `AWS_ACCESS_KEY_ID`
           - `AWS_SECRET_ACCESS_KEY`
           - `AWS_DEFAULT_REGION`
        """)
        return
    
    # Sidebar: Draft Management
    with st.sidebar:
        st.header("📋 Draft Management")
        
        # Get all active drafts
        all_drafts = st.session_state.draft_registry.get_all_drafts(status='active')
        completed_drafts = st.session_state.draft_registry.get_all_drafts(status='completed')
        
        # Show current draft info
        if st.session_state.draft_session_id:
            metadata = st.session_state.draft_registry.get_draft_metadata(st.session_state.draft_session_id)
            if metadata:
                st.success(f"**Active Draft:** {metadata.get('description', st.session_state.draft_session_id)}")
                st.caption(f"Format: {metadata.get('format_type', 'N/A')} | Status: {metadata.get('status', 'active')}")
            else:
                st.info(f"**Current:** {st.session_state.draft_session_id}")
        
        st.markdown("---")
        
        # Active Drafts List
        st.subheader("🔄 Switch Draft")
        if all_drafts:
            draft_options = {
                f"{d.get('description', d.get('draft_id'))} ({d.get('format_type', 'N/A')}) - "
                f"Round {d.get('current_round', 1)}/{d.get('num_rounds', 50)} - "
                f"{d.get('picks_completed', 0)} picks": d.get('draft_id')
                for d in all_drafts
            }
            
            selected_draft_label = st.selectbox(
                "Active Drafts",
                options=list(draft_options.keys()),
                index=0 if st.session_state.draft_session_id and st.session_state.draft_session_id in draft_options.values() 
                else None,
                help="Select a draft to view/edit"
            )
            
            if selected_draft_label:
                selected_draft_id = draft_options[selected_draft_label]
                if selected_draft_id != st.session_state.draft_session_id:
                    if st.button("Switch to This Draft"):
                        switch_draft(selected_draft_id)
        else:
            st.info("No active drafts. Create one below!")
        
        st.markdown("---")
        
        # Create New Draft
        st.subheader("➕ Create New Draft")
        with st.expander("New Draft Settings", expanded=False):
            new_format = st.selectbox("Format", ['50s', 'OC'], key='new_format')
            new_description = st.text_input(
                "Draft Name/Description", 
                value=f"{new_format} Draft {datetime.now().strftime('%Y-%m-%d')}",
                key='new_description'
            )
            col1, col2 = st.columns(2)
            with col1:
                new_teams = st.number_input("Teams", min_value=1, max_value=30, value=12, key='new_teams')
            with col2:
                new_rounds = st.number_input("Rounds", min_value=1, max_value=100, value=50, key='new_rounds')
            new_clock = st.number_input("Pick Clock (hours)", min_value=0.5, max_value=24.0, value=4.0, step=0.5, key='new_clock')
            
            if st.button("Create Draft", type="primary"):
                draft_id = create_new_draft(
                    format_type=new_format,
                    description=new_description,
                    num_teams=new_teams,
                    num_rounds=new_rounds,
                    pick_clock=new_clock
                )
                if draft_id:
                    st.success(f"Draft '{new_description}' created!")
                    switch_draft(draft_id)
                else:
                    st.error("Failed to create draft. Please try again.")
        
        st.markdown("---")
        
        # Draft Configuration (if draft is selected)
        if st.session_state.draft_tracker and st.session_state.draft_session_id:
            st.header("📊 Current Draft Info")
            
            summary = st.session_state.draft_tracker.get_draft_summary()
            metadata = st.session_state.draft_registry.get_draft_metadata(st.session_state.draft_session_id)
            
            if metadata:
                # Draft progress
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Round", f"{summary.get('current_round', 1)}/{summary.get('num_rounds', 50)}")
                with col2:
                    st.metric("Picks", f"{summary.get('total_drafted', 0)}/{summary.get('total_picks', 600)}")
                with col3:
                    st.metric("Progress", f"{summary.get('progress_pct', 0)}%")
                
                st.progress(summary.get('progress_pct', 0) / 100)
                
                # Draft details
                st.caption(f"**Format:** {summary.get('format_type', 'N/A')}")
                st.caption(f"**Teams:** {summary.get('num_teams', 12)}")
                st.caption(f"**Pick Clock:** {metadata.get('pick_clock_hours', 4)} hours")
                st.caption(f"**Status:** {summary.get('status', 'active').title()}")
                
                if summary.get('picks_remaining', 0) > 0:
                    st.caption(f"**Picks Remaining:** {summary.get('picks_remaining', 0)}")
                    st.caption(f"**Next Pick:** #{summary.get('next_pick', 1)}")
            
            st.markdown("---")
            
            # Filters
            st.header("🔍 Filters")
            
            # Position filter
            try:
                available_positions = st.session_state.athena_query.get_available_positions(st.session_state.format_type)
                selected_positions = st.multiselect(
                    "Position Groups",
                    options=available_positions,
                    default=[],
                    help="Filter by position group (leave empty for all positions)"
                )
            except:
                selected_positions = []
            
            # Team filter
            try:
                available_teams = st.session_state.athena_query.get_available_teams(st.session_state.format_type)
                selected_teams = st.multiselect(
                    "Teams",
                    options=available_teams,
                    default=[],
                    help="Filter by team (leave empty for all teams)"
                )
            except:
                selected_teams = []
            
            # Drafted status filter
            show_drafted = st.checkbox("Show Drafted Players", value=True)
            show_undrafted = st.checkbox("Show Undrafted Players", value=True)
            
            st.markdown("---")
            
            # Draft actions
            st.header("⚙️ Draft Actions")
            
            if st.button("🔄 Refresh Data (After dbt Update)"):
                # Force cache refresh by updating cache version
                # This ensures fresh data after dbt model refresh
                st.session_state.cache_version = datetime.now().strftime('%Y%m%d_%H%M%S')
                st.session_state.player_data = None
                st.success("Cache cleared! Fresh data will load from Athena on next query.")
                st.rerun()
            
            # Show cache info
            st.caption("💡 **Tip**: Use 'Refresh Data' after updating dbt models to get latest rankings")
            st.caption(f"🕐 **Cache**: Refreshes every 15 minutes automatically")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ Clear This Draft"):
                    if st.session_state.draft_tracker.clear_draft():
                        st.success("Draft cleared successfully!")
                        st.session_state.player_data = None
                        st.rerun()
            with col2:
                if st.button("🏁 Complete Draft"):
                    st.session_state.draft_registry.update_draft_metadata(
                        st.session_state.draft_session_id,
                        {'status': 'completed', 'completed_at': datetime.now().isoformat()}
                    )
                    st.success("Draft marked as completed!")
                    st.rerun()
    
    # Main content area
    if not st.session_state.draft_tracker or not st.session_state.draft_session_id:
        # No draft selected - show welcome/instructions
        st.header("Welcome to Fantasy Baseball Draft Tool! 🎉")
        st.info("""
        **Get Started:**
        1. Create a new draft using the sidebar (➕ Create New Draft)
        2. Or switch to an existing active draft
        3. Start tracking your picks!
        
        **Features for Slow Drafts:**
        - ✅ Multiple concurrent drafts (same or different formats)
        - ✅ 2-4 hour pick clocks supported
        - ✅ Up to 50 rounds with 12-15 teams
        - ✅ Drafts can last days/weeks
        - ✅ Automatic progress tracking (round, pick number)
        - ✅ Optimized caching (data stable during draft)
        """)
        
        if all_drafts:
            st.subheader("Your Active Drafts:")
            for draft in all_drafts[:5]:  # Show up to 5
                with st.expander(f"{draft.get('description', draft.get('draft_id'))} - {draft.get('format_type', 'N/A')}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Status:** {draft.get('status', 'active').title()}")
                        st.write(f"**Round:** {draft.get('current_round', 1)}/{draft.get('num_rounds', 50)}")
                    with col2:
                        st.write(f"**Picks:** {draft.get('picks_completed', 0)}/{draft.get('total_picks', 600)}")
                        st.write(f"**Progress:** {draft.get('progress_pct', 0)}%")
                    if st.button(f"Switch to This Draft", key=f"switch_{draft.get('draft_id')}"):
                        switch_draft(draft.get('draft_id'))
        
        return
    
    # Draft is selected - show player rankings
    summary = st.session_state.draft_tracker.get_draft_summary()
    metadata = st.session_state.draft_registry.get_draft_metadata(st.session_state.draft_session_id)
    
    st.header(f"{metadata.get('description', 'Draft') if metadata else 'Draft'} - {st.session_state.format_type} Format")
    
    # Show draft progress at top
    if metadata and summary.get('total_picks', 0) > 0:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Current Round", f"{summary.get('current_round', 1)}", f"of {summary.get('num_rounds', 50)}")
        with col2:
            st.metric("Picks Completed", summary.get('total_drafted', 0), f"of {summary.get('total_picks', 600)}")
        with col3:
            st.metric("Next Pick", f"#{summary.get('next_pick', 1)}")
        with col4:
            st.metric("Progress", f"{summary.get('progress_pct', 0)}%")
        
        st.progress(summary.get('progress_pct', 0) / 100)
        st.markdown("---")
    
    # Load player data
    try:
        if st.session_state.player_data is None:
            with st.spinner("Loading player data from Athena (cached for 15 min - refresh after dbt updates)..."):
                df = st.session_state.athena_query.query_mart_table(
                    format_type=st.session_state.format_type,
                    filters=None,  # Don't filter here, we'll filter in pandas for drafted status
                    order_by='rank',
                    cache_version=st.session_state.cache_version  # Use cache version to force refresh when needed
                )
                st.session_state.player_data = df
        
        df = st.session_state.player_data.copy()
        
        # Apply drafted status filtering
        drafted_ids = st.session_state.draft_tracker.get_drafted_players()
        df['is_drafted'] = df['id'].astype(str).isin([str(pid) for pid in drafted_ids])
        
        # Filter by drafted status
        if not show_drafted:
            df = df[~df['is_drafted']]
        if not show_undrafted:
            df = df[df['is_drafted']]
        
        # Apply position filter
        if selected_positions:
            df = df[df['pos_group'].isin(selected_positions)]
        
        # Apply team filter
        if selected_teams:
            df = df[df['team'].isin(selected_teams)]
        
        # Display player table
        st.subheader(f"Showing {len(df)} players")
        
        # Column selection for display
        display_columns = [
            'rank', 'name', 'team', 'pos', 'pos_group', 
            'value', 'sgp', 'sgpar', 'adp', 'rank_diff',
            'is_drafted'
        ]
        
        # Only show columns that exist in the dataframe
        available_columns = [col for col in display_columns if col in df.columns]
        
        # Create editable dataframe
        st.dataframe(
            df[available_columns].sort_values('rank'),
            use_container_width=True,
            hide_index=True
        )
        
        # Player actions section
        st.markdown("---")
        st.subheader("Mark Player as Drafted")
        
        # Player selector
        player_options = df[['id', 'name', 'team', 'pos']].apply(
            lambda x: f"{x['name']} ({x['team']}) - {x['pos']}", axis=1
        ).tolist()
        
        selected_player_idx = st.selectbox(
            "Select Player",
            options=range(len(player_options)),
            format_func=lambda x: player_options[x] if x < len(player_options) else ""
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ Mark as Drafted (Auto Pick #)", type="primary"):
                if selected_player_idx < len(df):
                    selected_player = df.iloc[selected_player_idx]
                    player_id = selected_player['id']
                    player_name = selected_player['name']
                    if st.session_state.draft_tracker.mark_player_drafted(
                        player_id=player_id,
                        player_name=player_name,
                        auto_increment=True
                    ):
                        st.success(f"✅ {player_name} marked as drafted (Pick #{summary.get('next_pick', 1)})!")
                        st.session_state.player_data = None  # Refresh data
                        st.rerun()
        
        with col2:
            if st.button("❌ Mark as Undrafted"):
                if selected_player_idx < len(df):
                    selected_player = df.iloc[selected_player_idx]
                    player_id = selected_player['id']
                    if st.session_state.draft_tracker.mark_player_undrafted(player_id, update_progress=True):
                        st.success(f"❌ {selected_player['name']} marked as undrafted!")
                        st.session_state.player_data = None  # Refresh data
                        st.rerun()
        
        # Show recently drafted players
        st.markdown("---")
        st.subheader("Recently Drafted Players")
        drafted_players = st.session_state.draft_tracker.get_drafted_players_with_picks()
        if drafted_players:
            recent = sorted(drafted_players, key=lambda x: x.get('draft_pick', 0), reverse=True)[:10]
            for pick in recent:
                st.write(f"**Pick #{pick.get('draft_pick', '?')}:** {pick.get('player_name', 'Unknown')} "
                        f"(ID: {pick.get('player_id')}) - Drafted at {pick.get('drafted_at', 'N/A')[:19]}")
        else:
            st.info("No players drafted yet. Use the selector above to mark players as drafted!")
        
    except Exception as e:
        st.error(f"Error loading player data: {str(e)}")
        st.info("""
        **Troubleshooting:**
        1. Ensure your dbt models have been built (`dbt run` or `dbt build`)
        2. Check that your Athena database and schema names match your configuration
        3. Verify you have permissions to query Athena tables
        4. Check the AWS region is correct
        """)


if __name__ == "__main__":
    main()
