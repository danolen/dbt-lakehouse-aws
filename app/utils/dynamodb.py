"""
DynamoDB utilities for tracking draft state

This module handles DynamoDB operations for tracking which players
have been drafted. Each draft session gets its own DynamoDB table.

Supports slow drafts with:
- Multiple concurrent drafts (same or different formats)
- Draft metadata (format, teams, rounds, status)
- Draft progress tracking (round, pick number)
- Long-term persistence (days/weeks for slow drafts)
"""

from typing import Optional, Dict, List
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
import streamlit as st
import json

from app.config.aws_config import AWSConfig


class DraftRegistry:
    """Registry to track all draft sessions"""
    
    REGISTRY_TABLE = f"{AWSConfig.DYNAMODB_TABLE_PREFIX}_registry"
    
    def __init__(self):
        self.dynamodb = AWSConfig.get_dynamodb_resource()
        self._ensure_registry_exists()
    
    def _ensure_registry_exists(self):
        """Create draft registry table if it doesn't exist"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            table.load()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                try:
                    table = self.dynamodb.create_table(
                        TableName=self.REGISTRY_TABLE,
                        KeySchema=[
                            {'AttributeName': 'draft_id', 'KeyType': 'HASH'}
                        ],
                        AttributeDefinitions=[
                            {'AttributeName': 'draft_id', 'AttributeType': 'S'}
                        ],
                        BillingMode='PAY_PER_REQUEST'
                    )
                    table.wait_until_exists()
                except ClientError as create_error:
                    st.warning(f"Could not create registry table: {str(create_error)}")
    
    def register_draft(self, draft_id: str, format_type: str, description: str = None,
                      num_teams: int = 12, num_rounds: int = 50, pick_clock_hours: float = 4) -> bool:
        """Register a new draft in the registry"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            item = {
                'draft_id': draft_id,
                'format_type': format_type,
                'description': description or f"{format_type} Draft",
                'num_teams': num_teams,
                'num_rounds': num_rounds,
                'pick_clock_hours': pick_clock_hours,
                'status': 'active',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'total_picks': num_teams * num_rounds,
                'current_round': 1,
                'current_pick': 1
            }
            table.put_item(Item=item)
            return True
        except ClientError as e:
            st.error(f"Error registering draft: {str(e)}")
            return False
    
    def get_all_drafts(self, status: str = None) -> List[Dict]:
        """Get all drafts, optionally filtered by status"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            response = table.scan()
            
            drafts = []
            for item in response.get('Items', []):
                if status is None or item.get('status') == status:
                    drafts.append(item)
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    if status is None or item.get('status') == status:
                        drafts.append(item)
            
            # Sort by updated_at descending (most recent first)
            drafts.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            return drafts
        except ClientError as e:
            st.warning(f"Error fetching drafts: {str(e)}")
            return []
    
    def get_draft_metadata(self, draft_id: str) -> Optional[Dict]:
        """Get metadata for a specific draft"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            response = table.get_item(Key={'draft_id': draft_id})
            return response.get('Item')
        except ClientError as e:
            return None
    
    def update_draft_metadata(self, draft_id: str, updates: Dict) -> bool:
        """Update draft metadata"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            
            # Build update expression
            update_expr = "SET updated_at = :updated_at"
            expr_vals = {':updated_at': datetime.now().isoformat()}
            
            for key, value in updates.items():
                if key != 'draft_id':  # Can't update the key
                    update_expr += f", {key} = :{key}"
                    expr_vals[f":{key}"] = value
            
            table.update_item(
                Key={'draft_id': draft_id},
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_vals
            )
            return True
        except ClientError as e:
            st.error(f"Error updating draft metadata: {str(e)}")
            return False
    
    def delete_draft_registry_entry(self, draft_id: str) -> bool:
        """Delete draft from registry (doesn't delete the draft table)"""
        try:
            table = self.dynamodb.Table(self.REGISTRY_TABLE)
            table.delete_item(Key={'draft_id': draft_id})
            return True
        except ClientError as e:
            st.error(f"Error deleting draft from registry: {str(e)}")
            return False


class DraftTracker:
    """Helper class for managing draft state in DynamoDB"""
    
    def __init__(self, session_id: str, format_type: str = None):
        """
        Initialize draft tracker for a session
        
        Args:
            session_id: Unique identifier for this draft session
            format_type: Format type ('50s' or 'oc') - used for metadata
        """
        self.session_id = session_id
        self.format_type = format_type
        self.table_name = f"{AWSConfig.DYNAMODB_TABLE_PREFIX}_{session_id}"
        self.dynamodb = AWSConfig.get_dynamodb_resource()
        self.registry = DraftRegistry()
        self._ensure_table_exists()
        
        # Initialize draft in registry if it doesn't exist
        if format_type:
            metadata = self.registry.get_draft_metadata(session_id)
            if not metadata:
                self.registry.register_draft(
                    draft_id=session_id,
                    format_type=format_type,
                    description=f"{format_type} Draft - {session_id}"
                )
    
    def _ensure_table_exists(self):
        """Create DynamoDB table if it doesn't exist"""
        try:
            # Check if table exists
            table = self.dynamodb.Table(self.table_name)
            table.load()
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                # Table doesn't exist, create it
                try:
                    table = self.dynamodb.create_table(
                        TableName=self.table_name,
                        KeySchema=[
                            {
                                'AttributeName': 'player_id',
                                'KeyType': 'HASH'  # Partition key
                            }
                        ],
                        AttributeDefinitions=[
                            {
                                'AttributeName': 'player_id',
                                'AttributeType': 'S'  # String
                            }
                        ],
                        BillingMode='PAY_PER_REQUEST'  # On-demand pricing (cost-efficient for personal use)
                    )
                    # Wait for table to be created
                    table.wait_until_exists()
                    st.success(f"Created draft tracking table: {self.table_name}")
                except ClientError as create_error:
                    st.error(f"Error creating DynamoDB table: {str(create_error)}")
                    raise
            else:
                st.error(f"Error checking DynamoDB table: {str(e)}")
                raise
    
    def mark_player_drafted(self, player_id: str, player_name: str = None, 
                           draft_pick: Optional[int] = None, auto_increment: bool = True) -> bool:
        """
        Mark a player as drafted
        
        Args:
            player_id: The player ID (matches 'id' field from mart tables)
            player_name: Optional player name for display
            draft_pick: Optional draft pick number (if None and auto_increment=True, uses next pick)
            auto_increment: If True, automatically assigns next pick number and updates draft progress
            
        Returns:
            True if successful, False otherwise
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            
            # Get or calculate draft pick number
            if draft_pick is None and auto_increment:
                summary = self.get_draft_summary()
                draft_pick = summary.get('next_pick', 1)
            
            item = {
                'player_id': str(player_id),
                'drafted': True,
                'drafted_at': datetime.now().isoformat(),
                'draft_pick': draft_pick
            }
            
            if player_name:
                item['player_name'] = player_name
            
            table.put_item(Item=item)
            
            # Update draft registry with progress
            if auto_increment and draft_pick:
                self._update_draft_progress(draft_pick)
            
            return True
        except ClientError as e:
            st.error(f"Error marking player as drafted: {str(e)}")
            return False
    
    def _update_draft_progress(self, current_pick: int):
        """Update draft progress in registry (round, pick number)"""
        try:
            metadata = self.registry.get_draft_metadata(self.session_id)
            if metadata:
                num_teams = metadata.get('num_teams', 12)
                num_rounds = metadata.get('num_rounds', 50)
                
                # Calculate round and pick number
                current_round = ((current_pick - 1) // num_teams) + 1
                pick_in_round = ((current_pick - 1) % num_teams) + 1
                
                # Check if round changed (snake draft - reverse order every other round)
                is_odd_round = (current_round % 2) == 1
                if not is_odd_round and num_teams > 1:
                    # Even rounds go in reverse order
                    pick_in_round = num_teams - pick_in_round + 1
                
                updates = {
                    'current_round': current_round,
                    'current_pick': current_pick,
                    'pick_in_round': pick_in_round,
                    'picks_completed': current_pick
                }
                
                # Calculate progress percentage
                total_picks = num_teams * num_rounds
                progress_pct = (current_pick / total_picks) * 100 if total_picks > 0 else 0
                updates['progress_pct'] = round(progress_pct, 1)
                
                # Check if draft is complete
                if current_pick >= total_picks:
                    updates['status'] = 'completed'
                    updates['completed_at'] = datetime.now().isoformat()
                elif metadata.get('status') == 'completed':
                    # Draft was completed but pick was removed, reactivate
                    updates['status'] = 'active'
                    if 'completed_at' in updates:
                        del updates['completed_at']
                
                self.registry.update_draft_metadata(self.session_id, updates)
        except Exception as e:
            # Don't fail draft operation if metadata update fails
            st.warning(f"Could not update draft progress: {str(e)}")
    
    def mark_player_undrafted(self, player_id: str, update_progress: bool = True) -> bool:
        """
        Mark a player as undrafted (remove from drafted list)
        
        Args:
            player_id: The player ID
            update_progress: If True, recalculates draft progress after removal
            
        Returns:
            True if successful, False otherwise
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            
            # Get the pick number before deleting (for progress update)
            pick_number = None
            if update_progress:
                response = table.get_item(Key={'player_id': str(player_id)})
                if 'Item' in response:
                    pick_number = response['Item'].get('draft_pick')
            
            table.delete_item(Key={'player_id': str(player_id)})
            
            # Recalculate progress if needed
            if update_progress and pick_number:
                self._recalculate_draft_progress()
            
            return True
        except ClientError as e:
            st.error(f"Error marking player as undrafted: {str(e)}")
            return False
    
    def _recalculate_draft_progress(self):
        """Recalculate draft progress after a pick is removed"""
        try:
            drafted = self.get_drafted_players_with_picks()
            if not drafted:
                # No picks, reset to beginning
                self.registry.update_draft_metadata(self.session_id, {
                    'current_round': 1,
                    'current_pick': 1,
                    'pick_in_round': 1,
                    'picks_completed': 0,
                    'progress_pct': 0,
                    'status': 'active'
                })
                return
            
            # Get max pick number
            max_pick = max(item.get('draft_pick', 0) for item in drafted if 'draft_pick' in item)
            
            if max_pick > 0:
                # Update to reflect max pick
                metadata = self.registry.get_draft_metadata(self.session_id)
                if metadata:
                    num_teams = metadata.get('num_teams', 12)
                    current_round = ((max_pick - 1) // num_teams) + 1
                    pick_in_round = ((max_pick - 1) % num_teams) + 1
                    
                    # Handle snake draft
                    is_odd_round = (current_round % 2) == 1
                    if not is_odd_round and num_teams > 1:
                        pick_in_round = num_teams - pick_in_round + 1
                    
                    total_picks = metadata.get('total_picks', num_teams * metadata.get('num_rounds', 50))
                    progress_pct = (max_pick / total_picks) * 100 if total_picks > 0 else 0
                    
                    self.registry.update_draft_metadata(self.session_id, {
                        'current_round': current_round,
                        'current_pick': max_pick,
                        'pick_in_round': pick_in_round,
                        'picks_completed': max_pick,
                        'progress_pct': round(progress_pct, 1),
                        'status': 'completed' if max_pick >= total_picks else 'active'
                    })
        except Exception as e:
            st.warning(f"Could not recalculate draft progress: {str(e)}")
    
    def get_drafted_players_with_picks(self) -> List[Dict]:
        """Get all drafted players with their pick information"""
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.scan()
            
            drafted = []
            for item in response.get('Items', []):
                if item.get('drafted', False):
                    drafted.append(item)
            
            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    if item.get('drafted', False):
                        drafted.append(item)
            
            # Sort by draft_pick if available
            drafted.sort(key=lambda x: x.get('draft_pick', 999999))
            return drafted
        except ClientError as e:
            st.error(f"Error fetching drafted players: {str(e)}")
            return []
    
    def is_player_drafted(self, player_id: str) -> bool:
        """
        Check if a player is drafted
        
        Args:
            player_id: The player ID
            
        Returns:
            True if drafted, False otherwise
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.get_item(Key={'player_id': str(player_id)})
            return 'Item' in response and response['Item'].get('drafted', False)
        except ClientError as e:
            st.warning(f"Error checking draft status: {str(e)}")
            return False
    
    def get_drafted_players(self) -> set:
        """
        Get set of all drafted player IDs
        
        Returns:
            Set of player IDs that have been drafted
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            response = table.scan()
            
            drafted_ids = set()
            for item in response.get('Items', []):
                if item.get('drafted', False):
                    drafted_ids.add(item['player_id'])
            
            # Handle pagination if needed (unlikely for draft tracking, but good practice)
            while 'LastEvaluatedKey' in response:
                response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
                for item in response.get('Items', []):
                    if item.get('drafted', False):
                        drafted_ids.add(item['player_id'])
            
            return drafted_ids
        except ClientError as e:
            st.error(f"Error fetching drafted players: {str(e)}")
            return set()
    
    def get_draft_summary(self) -> dict:
        """
        Get summary statistics of the draft including progress information
        
        Returns:
            Dictionary with draft stats including progress, rounds, etc.
        """
        try:
            # Get drafted players
            drafted = self.get_drafted_players_with_picks()
            total_drafted = len(drafted)
            
            picks = [item.get('draft_pick') for item in drafted if 'draft_pick' in item]
            next_pick = max(picks) + 1 if picks else 1
            
            # Get metadata from registry
            metadata = self.registry.get_draft_metadata(self.session_id)
            if metadata:
                return {
                    'total_drafted': total_drafted,
                    'total_picks_tracked': len(picks),
                    'next_pick': next_pick,
                    'format_type': metadata.get('format_type'),
                    'num_teams': metadata.get('num_teams', 12),
                    'num_rounds': metadata.get('num_rounds', 50),
                    'current_round': metadata.get('current_round', 1),
                    'current_pick': metadata.get('current_pick', 0),
                    'pick_in_round': metadata.get('pick_in_round', 1),
                    'progress_pct': metadata.get('progress_pct', 0),
                    'status': metadata.get('status', 'active'),
                    'total_picks': metadata.get('total_picks', metadata.get('num_teams', 12) * metadata.get('num_rounds', 50)),
                    'picks_remaining': metadata.get('total_picks', 600) - total_drafted,
                    'description': metadata.get('description', '')
                }
            else:
                # Fallback if no metadata
                return {
                    'total_drafted': total_drafted,
                    'total_picks_tracked': len(picks),
                    'next_pick': next_pick,
                    'format_type': self.format_type,
                    'current_round': 1,
                    'current_pick': len(picks),
                    'progress_pct': 0,
                    'status': 'active'
                }
        except ClientError as e:
            st.warning(f"Error getting draft summary: {str(e)}")
            return {
                'total_drafted': 0, 
                'total_picks_tracked': 0, 
                'next_pick': 1,
                'status': 'active'
            }
    
    def clear_draft(self) -> bool:
        """
        Clear all draft picks (reset draft state)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            drafted_ids = self.get_drafted_players()
            
            with table.batch_writer() as batch:
                for player_id in drafted_ids:
                    batch.delete_item(Key={'player_id': player_id})
            
            return True
        except ClientError as e:
            st.error(f"Error clearing draft: {str(e)}")
            return False
    
    def delete_table(self) -> bool:
        """
        Delete the draft tracking table (use with caution!)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            table = self.dynamodb.Table(self.table_name)
            table.delete()
            table.wait_until_not_exists()
            return True
        except ClientError as e:
            st.error(f"Error deleting table: {str(e)}")
            return False
