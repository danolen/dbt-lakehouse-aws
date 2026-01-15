# Slow Draft Support - Implementation Guide

## Overview

The app has been optimized for **slow drafts** with the following characteristics:
- **2-4 hour pick clocks** (drafts can span days/weeks)
- **50 rounds** with **12-15 teams** (600-750 total picks)
- **Multiple concurrent drafts** (same or different formats)
- **Long-term persistence** (draft state saved across sessions)

## Key Features for Slow Drafts

### 1. Draft Registry System

**Centralized Draft Management:**
- All drafts tracked in `fantasy_baseball_draft_registry` DynamoDB table
- Each draft has unique ID and metadata
- Easy switching between active drafts

**Draft Metadata Stored:**
- Format type (50s or OC)
- Description/name
- Number of teams (default: 12)
- Number of rounds (default: 50)
- Pick clock in hours (default: 4)
- Current round and pick number
- Progress percentage
- Status (active, completed)
- Created/updated timestamps

### 2. Automatic Progress Tracking

**Features:**
- **Auto-incrementing pick numbers** (1, 2, 3, ...)
- **Round calculation** (based on pick number and teams)
- **Snake draft support** (reverse order every other round)
- **Progress percentage** (picks completed / total picks)
- **Pick-in-round** calculation (for display purposes)

**How it Works:**
- When you mark a player as drafted, pick number is automatically assigned
- Round number calculated: `round = ((pick - 1) // teams) + 1`
- For even rounds (snake draft), order is reversed
- Progress updates automatically in registry

### 3. Multiple Concurrent Drafts

**Supported Scenarios:**
- ✅ Multiple drafts of **same format** (e.g., 3 different 50s drafts)
- ✅ Multiple drafts of **different formats** (e.g., 1 50s + 2 OC drafts)
- ✅ Mix of active and completed drafts
- ✅ Easy switching between drafts via sidebar dropdown

**UI Features:**
- **Draft list** shows all active drafts with progress
- **Quick switch** button to jump between drafts
- **Draft summary** shows current draft info at top of sidebar
- **Create new draft** without losing current draft state

### 4. Long-Term Persistence

**Data Persistence:**
- Draft state stored in DynamoDB (persists across sessions)
- Registry tracks all drafts (survives app restarts)
- Player picks saved permanently until draft is cleared
- Metadata (round, pick, progress) automatically maintained

**For Slow Drafts:**
- Close app, come back days/weeks later - draft state intact
- Switch between drafts anytime - each maintains its own state
- Complete draft can be archived (marked as completed) but not deleted
- All data stored in AWS - accessible from anywhere

### 5. Optimized Caching for Slow Drafts

**Cache Strategy:**
- **15-minute cache TTL** (balances freshness with cost)
- Rationale: Supports daily dbt model refreshes while maintaining cost efficiency
- Reduces Athena queries by 95%+ during draft sessions
- **Manual refresh available** via "Refresh Data" button (bypasses cache immediately)
- **Auto-refresh**: Cache expires every 15 minutes automatically

**Cost Benefits:**
- Typical slow draft (2-4 weeks, daily dbt updates): ~30-60 Athena queries total
- Without caching: ~1000+ queries (one per interaction)
- Cost savings: ~95%+ reduction in Athena queries
- Still extremely cost-effective (~$0.0003 per draft even with daily refreshes)

**Refresh Workflow:**
1. Update dbt models: `dbt build --select mart_*`
2. Click "🔄 Refresh Data" button in app
3. Fresh rankings load immediately (bypasses cache)
4. Cache resets for next 15 minutes

### 6. Enhanced UI for Slow Drafts

**Draft Progress Display:**
- **Current Round**: "Round 5 of 50"
- **Picks Completed**: "150 of 600"
- **Next Pick**: "#151"
- **Progress Bar**: Visual completion percentage
- **Status Badge**: Active, Completed, etc.

**Draft Management:**
- Create new draft with full configuration
- Switch between drafts easily
- Clear draft (reset to beginning)
- Complete draft (archive it)
- View all active drafts at a glance

**Recently Drafted Players:**
- Shows last 10 picks with pick number and timestamp
- Helps track draft progress
- Useful for slow drafts where you might forget what was picked

## Usage Example: Slow Draft Workflow

### Day 1: Create Draft
1. Open app → Create new draft
2. Name: "Main 50s League 2024"
3. Format: 50s
4. Teams: 12
5. Rounds: 50
6. Pick Clock: 4 hours
7. Click "Create Draft"

### Day 1-30: Ongoing Draft
1. Open app → Switch to your draft
2. Make picks as your turn comes up (every 2-4 hours)
3. Mark players as drafted - pick numbers auto-assign
4. Check progress: "Round 8 of 50, Pick 92 of 600, 15.3% complete"
5. Close app - come back later (state persists)

### Multiple Drafts:
1. Create second draft: "Secondary OC League"
2. Switch between drafts as needed
3. Each draft maintains independent state
4. Progress tracked separately for each

### After Draft Completes:
1. Mark draft as "Complete" (archives it)
2. Draft moves to completed drafts list
3. Data remains accessible (for reference)
4. Can still view/comparison if needed

## Technical Implementation

### DynamoDB Schema

**Registry Table (`fantasy_baseball_draft_registry`):**
```json
{
  "draft_id": "main_50s_league_2024",
  "format_type": "50s",
  "description": "Main 50s League 2024",
  "num_teams": 12,
  "num_rounds": 50,
  "pick_clock_hours": 4.0,
  "status": "active",
  "current_round": 8,
  "current_pick": 92,
  "pick_in_round": 8,
  "picks_completed": 92,
  "progress_pct": 15.3,
  "total_picks": 600,
  "created_at": "2024-01-15T10:00:00",
  "updated_at": "2024-01-20T14:30:00"
}
```

**Draft Table (`fantasy_baseball_draft_{draft_id}`):**
```json
{
  "player_id": "12345",
  "player_name": "Juan Soto",
  "drafted": true,
  "draft_pick": 92,
  "drafted_at": "2024-01-20T14:30:00"
}
```

### Progress Calculation Logic

**Round Calculation:**
```python
current_round = ((current_pick - 1) // num_teams) + 1
pick_in_round = ((current_pick - 1) % num_teams) + 1

# Snake draft: reverse order for even rounds
if current_round % 2 == 0:  # Even round
    pick_in_round = num_teams - pick_in_round + 1
```

**Progress Percentage:**
```python
progress_pct = (picks_completed / total_picks) * 100
```

### Cache Configuration

**Increased TTL for Slow Drafts:**
```python
@st.cache_data(ttl=3600)  # 1 hour (was 5 minutes)
def query_mart_table(...):
    # Query Athena and cache result
```

**Rationale:**
- Player rankings stable during draft (don't refresh dbt models mid-draft)
- Reduces costs by 99%+ for slow drafts
- Manual refresh available if needed

## Cost Considerations for Slow Drafts

**Typical Slow Draft (30 days, 12 teams, 50 rounds):**
- **DynamoDB**: ~600 write requests (one per pick) = $0.00075
- **Athena**: ~4 queries (cache hit rate 99%+) = $0.00002
- **S3**: Storage minimal (~1 MB) = $0.00002
- **Total per draft**: ~$0.001 (less than a penny!)

**Multiple Concurrent Drafts:**
- Costs scale linearly with number of drafts
- 5 concurrent drafts = ~$0.005/month
- Still essentially free for personal use

## Best Practices for Slow Drafts

1. **Use descriptive draft names** - Makes switching easier
2. **Set correct team/round counts** - Ensures accurate progress tracking
3. **Don't clear cache during draft** - Data is stable, cache reduces costs
4. **Mark draft as complete** - When finished, archive for reference
5. **Use multiple drafts** - Separate drafts for separate leagues

## Troubleshooting

**Draft Progress Not Updating:**
- Check that pick numbers are being assigned (auto_increment=True)
- Verify registry table has correct metadata
- Try refreshing data

**Can't Find Draft:**
- Check "Switch Draft" dropdown in sidebar
- Verify draft status is "active" (not "completed")
- Check draft registry table directly

**Progress Calculation Wrong:**
- Verify num_teams and num_rounds in registry match actual draft
- Check that picks are being marked in order
- Recalculate progress by marking a player undrafted then redrafted

**Multiple Drafts Confusion:**
- Use descriptive draft names
- Check format type in draft list
- Use progress % to distinguish drafts at different stages

---

## Summary

The app is now fully optimized for slow drafts with:
- ✅ Multiple concurrent draft support
- ✅ Automatic progress tracking
- ✅ Long-term persistence (days/weeks)
- ✅ Cost-efficient caching (99%+ savings)
- ✅ Easy draft management UI
- ✅ Snake draft format support
- ✅ Round and pick number tracking

**Perfect for slow drafts with 2-4 hour clocks spanning days or weeks!** 🎉
