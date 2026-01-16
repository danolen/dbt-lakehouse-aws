"""
Simple Fantasy Baseball Draft Tool

This is a basic Streamlit app to view player rankings from your dbt mart tables.
We'll build this up incrementally, keeping it simple and understandable.
"""

import streamlit as st
import pandas as pd
import os
from datetime import datetime
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
# This makes it easy to set config without hardcoding values
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Fantasy Baseball Draft Tool",
    page_icon="⚾",
    layout="wide"
)

# Title
st.title("⚾ Fantasy Baseball Draft Tool")
st.markdown("View player rankings from your dbt mart tables")

# Configuration - read from environment variables, with defaults as fallback
# You can set these in a .env file or as environment variables
ATHENA_DATABASE = os.getenv("ATHENA_DATABASE", "AwsDataCatalog")
ATHENA_SCHEMA = os.getenv("ATHENA_SCHEMA", "dbt_main")
ATHENA_REGION = os.getenv("ATHENA_REGION", "us-east-1")
ATHENA_S3_OUTPUT = os.getenv("ATHENA_S3_OUTPUT", "s3://dn-lakehouse-dev/logs/athena-results/")

# Format selection
format_type = st.selectbox("Select Format", ["50s", "OC"])

# Table name based on format
table_name = f"mart_preseason_overall_rankings_{format_type.lower()}"

# CACHING EXPLANATION:
# st.session_state is Streamlit's way to store data in memory between button clicks
# We'll use it to store the player data so we don't query Athena every time
# Key: format_type (so 50s and OC have separate cached data)
cache_key = f"player_data_{format_type}"
timestamp_key = f"cache_timestamp_{format_type}"

# Check if we already have data cached for this format
if cache_key not in st.session_state:
    # No cached data - we'll need to load it
    st.session_state[cache_key] = None
    st.session_state[timestamp_key] = None

# Button to refresh/load data
col1, col2 = st.columns(2)
with col1:
    load_button = st.button("Load Player Rankings")
with col2:
    refresh_button = st.button("🔄 Refresh Data")

# If refresh button clicked, clear the cache
if refresh_button:
    st.session_state[cache_key] = None
    st.session_state[timestamp_key] = None
    st.info("Cache cleared! Click 'Load Player Rankings' to fetch fresh data.")

# Load data if button clicked OR if we don't have cached data yet
if load_button or st.session_state[cache_key] is None:
    with st.spinner("Loading data from Athena..."):
        try:
            # Connect to Athena
            conn = connect(
                s3_staging_dir=ATHENA_S3_OUTPUT,
                region_name=ATHENA_REGION,
                schema_name=ATHENA_SCHEMA,
                cursor_class=PandasCursor
            )
            
            # Simple query - get all players
            query = f"SELECT * FROM {ATHENA_SCHEMA}.{table_name} ORDER BY rank"
            
            # Execute query and get results as pandas DataFrame
            cursor = conn.cursor()
            df = cursor.execute(query).as_pandas()
            
            # Store in session_state (this is the caching part!)
            # Next time the page reruns, this data will still be here
            st.session_state[cache_key] = df
            st.session_state[timestamp_key] = datetime.now()
            
            st.success(f"Loaded {len(df)} players from Athena!")
            
        except Exception as e:
            st.error(f"Error loading data: {str(e)}")
            st.info("""
            **Troubleshooting:**
            1. Make sure AWS credentials are configured (run `aws configure`)
            2. Check your .env file or environment variables
            3. Make sure your dbt models are built (`dbt build --select mart_*`)
            4. Check that the schema and table names match your setup
            """)

# Display the data if we have it cached
if st.session_state[cache_key] is not None:
    df = st.session_state[cache_key].copy()  # Make a copy so we don't modify the cached data
    cached_time = st.session_state[timestamp_key]
    
    # Format the timestamp nicely
    if cached_time:
        time_str = cached_time.strftime("%Y-%m-%d %H:%M:%S")
        st.caption(f"📅 Data cached at: {time_str}")
    
    st.markdown("---")
    st.subheader("Filters & Sorting")
    
    # FILTERING SECTION
    # We'll add filters in columns to keep it organized
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Filter by position (multi-select)
        # Get unique positions from the data - players can have multiple positions
        if 'pos' in df.columns:
            # Get all unique position values (like "SS", "2B/SS", "OF", etc.)
            all_positions = set()
            for pos_str in df['pos'].dropna():
                # Split by common separators and add individual positions
                if isinstance(pos_str, str):
                    # Handle formats like "SS", "2B/SS", "OF/1B", etc.
                    positions = pos_str.replace('/', ',').split(',')
                    for p in positions:
                        all_positions.add(p.strip())
            
            positions_list = sorted(list(all_positions))
            selected_positions = st.multiselect(
                "Position (can select multiple)", 
                positions_list,
                help="Select one or more positions. Shows players who have ANY of these positions."
            )
        else:
            selected_positions = []
    
    with col2:
        # Filter by team
        if 'team' in df.columns:
            teams = ['All'] + sorted(df['team'].dropna().unique().tolist())
            selected_team = st.selectbox("Team", teams)
        else:
            selected_team = 'All'
    
    with col3:
        # Search by player name
        search_name = st.text_input("Search Player Name", "")
    
    # Apply filters to the dataframe
    # Start with all data, then filter step by step
    filtered_df = df.copy()
    
    # Filter by position (multi-select)
    # Show players whose 'pos' column contains ANY of the selected positions
    if selected_positions and 'pos' in filtered_df.columns:
        # Create a mask: True if pos contains any of the selected positions
        mask = filtered_df['pos'].astype(str).apply(
            lambda pos: any(sel_pos in str(pos) for sel_pos in selected_positions)
        )
        filtered_df = filtered_df[mask]
    
    # Filter by team
    if selected_team != 'All' and 'team' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['team'] == selected_team]
    
    # Search by name (case-insensitive)
    if search_name and 'name' in filtered_df.columns:
        filtered_df = filtered_df[
            filtered_df['name'].str.contains(search_name, case=False, na=False)
        ]
    
    st.markdown("---")
    
    # SORTING SECTION
    st.subheader("Sorting")
    
    # Let user choose which column to sort by
    sort_col1, sort_col2 = st.columns(2)
    
    with sort_col1:
        # Get numeric columns for sorting (more useful than text columns)
        numeric_cols = filtered_df.select_dtypes(include=['int64', 'float64']).columns.tolist()
        # Also include some common text columns that make sense to sort
        text_cols = ['name', 'team', 'pos'] if 'name' in filtered_df.columns else []
        sort_options = ['rank'] + [col for col in numeric_cols if col != 'rank'] + text_cols
        
        sort_column = st.selectbox("Sort by", sort_options, index=0)
    
    with sort_col2:
        sort_order = st.selectbox("Order", ["Ascending", "Descending"])
    
    # Apply sorting
    ascending = sort_order == "Ascending"
    if sort_column in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by=sort_column, ascending=ascending)
    
    # Display the filtered and sorted data
    st.markdown("---")
    st.subheader(f"Results: {len(filtered_df)} players")
    
    st.dataframe(filtered_df, use_container_width=True)
    
    # Show summary
    if len(filtered_df) < len(df):
        st.caption(f"Filtered from {len(df)} total players (use Refresh button to reload)")
    else:
        st.caption(f"Showing all {len(df)} players (use Refresh button to reload)")
