# Caching Explanation - What Gets Cached?

## Overview

The app uses **Streamlit's `@st.cache_data` decorator** to cache query results, reducing expensive Athena queries. Here's exactly what's being cached and how it works.

---

## What Is Being Cached?

### The Cached Data: Full Player Rankings DataFrame

**What's cached:**
- The **entire pandas DataFrame** returned from `query_mart_table()`
- Contains **ALL player rankings** from your mart table (50s or OC format)
- Includes all columns: rank, name, team, position, stats, SGP values, ADP, etc.

**Example cached data:**
```python
# What gets cached (simplified):
   rank    name              team   pos  pos_group  value  sgp  adp  rank_diff  ...
0  1       "Player Name"     "NYY"  "OF" "OF"       25.5   150  5    4
1  2       "Another Player"  "LAD"  "1B" "1B"       24.2   148  8    6
...
# ~1000-2000 rows total
```

### Cache Location: In-Memory (Streamlit Session)

- **Storage**: Cached in **memory** (not disk)
- **Scope**: Per Streamlit session (per user/browser tab)
- **Duration**: 5 minutes (300 seconds)
- **Size**: Minimal (~1-5 MB for typical player rankings data)

---

## How Caching Works

### Cache Key (What Makes Cached Entries Unique)

The cache key is based on **function arguments**:

```python
@st.cache_data(ttl=300)  # Cache for 5 minutes
def query_mart_table(
    format_type: str = "50s",  # Part of cache key
    filters: Optional[dict] = None,  # Part of cache key
    order_by: Optional[str] = None,  # Part of cache key
    limit: Optional[int] = None  # Part of cache key
) -> pd.DataFrame:
```

**Different cache entries for:**
- `format_type="50s"` vs `format_type="oc"`
- `filters=None` vs `filters={'pos_group': 'OF'}`
- `order_by='rank'` vs `order_by='value'`
- Different `limit` values

### Current App Behavior

**How the app calls the cached function:**

```python
# From app/app.py line 152-156:
df = st.session_state.athena_query.query_mart_table(
    format_type=format_type,  # "50s" or "oc"
    filters=None,  # No filters - gets FULL table
    order_by='rank'
)
```

**What this means:**
- **ONE cache entry** per format type (50s vs OC)
- **Full table** is cached (all ~1000-2000 players)
- **Client-side filtering** happens in pandas AFTER getting cached data
- **Efficient**: One Athena query can be filtered multiple ways

### Cache Lifecycle

```
User Action                    Cache Status          Athena Query?
------------------------       -----------           -------------
1. First load                   MISS                 ✅ Yes (full table)
2. Filter by position          HIT                   ❌ No (uses cache)
3. Filter by team              HIT                   ❌ No (uses cache)
4. Switch format (50s→OC)      MISS (new key)        ✅ Yes (different table)
5. After 5 minutes             EXPIRED               ✅ Yes (refresh)
6. User interaction            HIT (if <5 min)       ❌ No (uses cache)
```

---

## What Is NOT Cached?

### Not Cached (Recomputed Each Time):

1. **Draft Status** (`is_drafted` column)
   - Fetched from DynamoDB each time
   - Added to DataFrame in pandas (client-side)
   - Reason: Changes frequently during draft

2. **Position Lists** (for dropdowns)
   - `get_available_positions()` - No cache
   - `get_available_teams()` - No cache
   - Reason: These queries are very cheap (<1 KB data)

3. **Client-Side Filtering**
   - Position filter, team filter, drafted status filter
   - Applied in pandas after getting cached data
   - Reason: Allows one cached query to support multiple filter combinations

### Why This Design?

**Smart caching strategy:**
- ✅ **Cache expensive operations**: Full table queries to Athena (costs money)
- ❌ **Don't cache frequently changing data**: Draft status from DynamoDB
- ✅ **Cache once, filter many**: One cached query supports all filter combinations

---

## Cache Invalidation

### Automatic Invalidation (TTL-based):

1. **Time-based**: Cache expires after **5 minutes (300 seconds)**
   - Next query after expiration will hit Athena
   - Ensures data is relatively fresh

### Manual Invalidation:

1. **"Refresh Data" button** (forces immediate cache refresh):
   ```python
   if st.button("🔄 Refresh Data (After dbt Update)"):
       st.session_state.cache_version = datetime.now().strftime('%Y%m%d_%H%M%S')
       st.session_state.player_data = None
       st.rerun()
   ```
   - Updates cache version (forces Streamlit cache miss)
   - Clears session state cache
   - **Forces immediate re-query** from Athena (bypasses cache)
   - Use this after refreshing dbt models to get latest rankings

2. **Changing format type** (50s ↔ OC):
   - Creates new cache entry
   - Old cache remains until expiration

3. **Restarting Streamlit app**:
   - All caches cleared
   - Fresh queries on next load

---

## Cache Performance Impact

### Cost Savings:

**Without caching:**
- Every user interaction = 1 Athena query
- Typical draft session = 50-100 queries
- Cost: ~$0.0005 per session

**With caching (5 minutes):**
- First load = 1 Athena query
- Subsequent interactions (<5 min) = 0 queries
- Typical draft session = 1-2 queries total
- Cost: ~$0.00001 per session (95%+ savings!)

### Speed Improvements:

- **First load**: ~2-5 seconds (Athena query)
- **Cached loads**: ~0.01 seconds (in-memory access)
- **200x faster** for cached data

---

## Cache Configuration Options

### Current Setting:

```python
@st.cache_data(ttl=900)  # 15 minutes (supports daily dbt model refreshes)
```

**Why 15 minutes?**
- ✅ Supports daily dbt model refreshes (common as season approaches)
- ✅ Auto-refreshes every 15 minutes (ensures relatively fresh data)
- ✅ Manual refresh button bypasses cache immediately (use after dbt updates)
- ✅ Still 95%+ cost savings vs no caching
- ✅ Balance between freshness and cost efficiency

### Alternative Options:

**1. Longer Cache (Lower Costs, Staler Data):**
```python
@st.cache_data(ttl=3600)  # 1 hour
# Good if: Data doesn't change during draft session
# Trade-off: Data might be stale if you refresh dbt models mid-draft
```

**2. Shorter Cache (Fresher Data, Higher Costs):**
```python
@st.cache_data(ttl=60)  # 1 minute
# Good if: Data changes frequently
# Trade-off: More Athena queries (but still minimal cost)
```

**3. No Expiration (User-Controlled Refresh):**
```python
@st.cache_data()  # No TTL - cache until manual refresh
# Good if: You want full control via "Refresh" button
# Trade-off: Data could be stale if you forget to refresh, but zero cost after first load
# Note: Not recommended if refreshing dbt models daily
```

**4. Current Approach (15 minutes + Manual Refresh):**
```python
@st.cache_data(ttl=900)  # 15 minutes
# Best of both worlds:
# - Auto-refreshes every 15 minutes (ensures data freshness)
# - Manual refresh button bypasses cache immediately (use after dbt updates)
# - Supports daily dbt model refreshes without being too aggressive
# - Still 95%+ cost savings
```

**5. Per-User Cache Key (Multi-User Support):**
```python
@st.cache_data(ttl=900, show_spinner=True)
def query_mart_table(self, format_type: str, user_id: str = None, ...):
    # Include user_id in cache key if you add multi-user support
```

---

## Understanding Cache vs Session State

### Two Levels of Caching:

1. **Streamlit Cache** (`@st.cache_data`):
   - Managed by Streamlit
   - Survives Streamlit reruns (button clicks, filter changes)
   - Expires after TTL
   - Shared across all interactions in session

2. **Session State** (`st.session_state.player_data`):
   - Managed by app code
   - Cleared by "Refresh Data" button
   - Persists across page reruns
   - Used to avoid re-calling cached function unnecessarily

**Flow:**
```
User loads app
  ↓
Check session_state.player_data (None? Yes)
  ↓
Call query_mart_table() (check Streamlit cache)
  ↓
Cache MISS? Query Athena, cache result
  ↓
Store in session_state.player_data
  ↓
User filters/changes something
  ↓
Check session_state.player_data (exists? Yes)
  ↓
Use cached data, filter in pandas
  ↓
NO Athena query needed!
```

---

## Monitoring Cache Performance

### To See Cache Hits/Misses:

Add this temporarily to debug:

```python
import streamlit as st

# Add this to see cache stats (temporary debugging)
if st.checkbox("Show Cache Stats"):
    cache_info = st.cache_data.get_stats()
    st.json(cache_info)
```

### Expected Behavior:

- **Cache hits**: 90%+ of interactions (after initial load)
- **Cache misses**: Only on first load, format switch, or after 5 minutes
- **Athena queries**: Should be minimal (1-2 per draft session)

---

## Recommendations

### For Your Use Case (Slow Drafts with Daily dbt Refreshes):

**Current setting (15 minutes) is ideal because:**

1. ✅ **Cost-efficient**: 95%+ reduction in Athena queries (even with daily refreshes)
2. ✅ **Fast**: Near-instant responses after initial load
3. ✅ **Fresh enough**: 15 minutes ensures data stays relatively current
4. ✅ **Manual refresh**: "Refresh Data" button bypasses cache immediately (use after dbt updates)
5. ✅ **Daily updates supported**: Can refresh dbt models daily without excessive costs
6. ✅ **Balance**: Sweet spot between freshness and cost efficiency

### Refresh Workflow for Daily dbt Updates:

1. **Update dbt models** (as frequently as daily as season approaches):
   ```bash
   dbt build --select mart_*
   ```

2. **Refresh app data**:
   - Click "🔄 Refresh Data (After dbt Update)" button
   - Fresh rankings load immediately (bypasses cache)
   - Cache resets for next 15 minutes

3. **Automatic refresh**: If you forget to click refresh, cache auto-updates every 15 minutes

**Consider longer cache (1 hour) if:**
- You won't refresh dbt models during a draft session
- You want even lower costs (though already minimal)
- Data stability is more important than freshness

**Keep current (5 minutes) if:**
- You might refresh dbt models during draft
- You want data to auto-refresh periodically
- Current costs are already acceptable

---

## Summary

**What's cached:**
- ✅ Full player rankings DataFrame (~1000-2000 rows, all columns)
- ✅ One cache entry per format type (50s vs OC)
- ✅ Cached for 5 minutes (300 seconds)
- ✅ Stored in Streamlit session memory

**What's NOT cached:**
- ❌ Draft status (fetched from DynamoDB each time)
- ❌ Position/team lists (cheap queries, not worth caching)
- ❌ Client-side filtering (applied in pandas after cache)

**Cache benefits:**
- 💰 **95%+ cost savings** (1-2 queries vs 50-100 per session)
- ⚡ **200x faster** (0.01s vs 2-5s for cached data)
- ✅ **Smart invalidation** (5 min TTL + manual refresh button)

**Bottom line:** The cache stores the full player rankings table, allowing all filtering to happen client-side without additional Athena queries. This is an efficient design that maximizes cost savings while maintaining good performance.
