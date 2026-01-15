"""
Database utilities for querying Athena tables

This module provides functions to query the mart tables in Athena.
Uses PyAthena for SQL execution, which handles pagination and result sets.
"""

import pandas as pd
from pyathena import connect
from pyathena.pandas.cursor import PandasCursor
from typing import Optional
import streamlit as st

from app.config.aws_config import AWSConfig


class AthenaQuery:
    """Helper class for querying Athena tables"""
    
    def __init__(self):
        self.config = AWSConfig
    
    def get_connection(self):
        """Get PyAthena connection"""
        return connect(
            s3_staging_dir=AWSConfig.ATHENA_S3_OUTPUT_LOCATION,
            region_name=AWSConfig.ATHENA_REGION,
            schema_name=AWSConfig.ATHENA_SCHEMA,
            cursor_class=PandasCursor
        )
    
    @st.cache_data(ttl=900)  # Cache for 15 minutes (balances freshness with cost - refresh dbt models daily)
    def query_mart_table(
        self, 
        format_type: str = "50s",
        filters: Optional[dict] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        cache_version: Optional[str] = None  # Use this to force cache invalidation
    ) -> pd.DataFrame:
        """
        Query the mart preseason rankings table
        
        Args:
            format_type: '50s' or 'oc' to determine which mart table to query
            filters: Dictionary of filters to apply, e.g. {'pos_group': 'OF', 'drafted': False}
            order_by: Column name to order by (optional, defaults to 'rank')
            limit: Maximum number of rows to return (optional)
            cache_version: Optional version string to force cache refresh (e.g., timestamp)
            
        Returns:
            DataFrame with player rankings data
        """
        table_name = AWSConfig.get_mart_table_name(format_type)
        
        # Build WHERE clause
        where_clauses = []
        if filters:
            for key, value in filters.items():
                if value is not None:
                    if isinstance(value, bool):
                        where_clauses.append(f"{key} = {value}")
                    elif isinstance(value, str):
                        where_clauses.append(f"{key} = '{value}'")
                    elif isinstance(value, (int, float)):
                        where_clauses.append(f"{key} = {value}")
                    elif isinstance(value, list):
                        # Handle IN clause
                        values = [f"'{v}'" if isinstance(v, str) else str(v) for v in value]
                        where_clauses.append(f"{key} IN ({', '.join(values)})")
        
        where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        # Build ORDER BY clause
        order_by_clause = f"ORDER BY {order_by}" if order_by else "ORDER BY rank"
        
        # Build LIMIT clause
        limit_clause = f"LIMIT {limit}" if limit else ""
        
        # Construct query
        query = f"""
        SELECT *
        FROM {AWSConfig.ATHENA_SCHEMA}.{table_name}
        WHERE {where_clause}
        {order_by_clause}
        {limit_clause}
        """
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                df = cursor.execute(query).as_pandas()
                return df
        except Exception as e:
            st.error(f"Error querying database: {str(e)}")
            raise
    
    def get_available_positions(self, format_type: str = "50s") -> list:
        """Get list of unique positions in the dataset"""
        table_name = AWSConfig.get_mart_table_name(format_type)
        
        query = f"""
        SELECT DISTINCT pos_group
        FROM {AWSConfig.ATHENA_SCHEMA}.{table_name}
        WHERE pos_group IS NOT NULL
        ORDER BY pos_group
        """
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                df = cursor.execute(query).as_pandas()
                return df['pos_group'].tolist()
        except Exception as e:
            st.warning(f"Could not fetch positions: {str(e)}")
            return []
    
    def get_available_teams(self, format_type: str = "50s") -> list:
        """Get list of unique teams in the dataset"""
        table_name = AWSConfig.get_mart_table_name(format_type)
        
        query = f"""
        SELECT DISTINCT team
        FROM {AWSConfig.ATHENA_SCHEMA}.{table_name}
        WHERE team IS NOT NULL
        ORDER BY team
        """
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                df = cursor.execute(query).as_pandas()
                return df['team'].tolist()
        except Exception as e:
            st.warning(f"Could not fetch teams: {str(e)}")
            return []
