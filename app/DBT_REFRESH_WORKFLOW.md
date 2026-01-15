# Daily dbt Refresh Workflow - Best Practices

## Overview

The app supports **daily dbt model refreshes** during slow drafts, especially as the season approaches and projections become more accurate. Here's how to manage this workflow efficiently.

---

## Recommended Workflow

### When to Refresh dbt Models

**Daily Refreshes (Recommended as Season Approaches):**
- Projections become more accurate closer to season start
- Injuries, trades, and roster changes update frequently
- Daily refreshes ensure you have the latest rankings

**Weekly Refreshes (Earlier in Draft Season):**
- If drafts are earlier in preseason, weekly may be sufficient
- Projections are less volatile earlier in the year
- Reduces unnecessary model rebuilds

### Step-by-Step Process

**1. Update dbt Models:**
```bash
# From your dbt project directory
dbt build --select mart_*

# Or just rebuild mart models
dbt run --select mart_*
```

**2. Refresh App Data:**
- Open your Streamlit draft tool
- Navigate to your active draft
- Click **"🔄 Refresh Data (After dbt Update)"** button
- Fresh rankings load immediately (bypasses cache)

**3. Verify Updated Rankings:**
- Check that player rankings reflect latest projections
- Player values, SGP, and rankings should update
- Draft state (picked players) remains unchanged

---

## Cache Strategy Explained

### Automatic Cache (15 Minutes)

**How it works:**
- Data cached for **15 minutes** after each query
- Cache expires automatically after 15 minutes
- Next query after expiration refreshes from Athena
- Ensures data stays relatively fresh

**When to rely on auto-refresh:**
- If you forget to click refresh button
- If dbt models refresh happens less frequently
- If you don't need immediate updates

### Manual Cache Refresh (Immediate)

**How it works:**
- Click "🔄 Refresh Data" button
- Updates `cache_version` parameter (forces cache miss)
- Immediately queries Athena for fresh data
- Bypasses 15-minute cache completely

**When to use manual refresh:**
- ✅ **After updating dbt models** (recommended)
- ✅ When you need latest rankings immediately
- ✅ Before making important draft decisions
- ✅ After significant projection updates

---

## Cost Considerations

### With Daily dbt Refreshes

**Typical Slow Draft (30 days, daily refreshes):**
- **Manual refresh daily**: ~30 Athena queries
- **Auto-refresh every 15 min**: ~2880 queries (not recommended)
- **Manual refresh only**: ~30 queries per draft
- **Cost**: ~$0.00015 per draft (still essentially free!)

**Cost Breakdown:**
- DynamoDB: ~$0.01 (draft tracking)
- Athena (30 queries @ ~$0.000005 each): ~$0.00015
- S3: ~$0.00001
- **Total: ~$0.01 per draft** (even with daily refreshes!)

### Cost Optimization Tips

1. **Use manual refresh** only after dbt updates (don't rely on auto-refresh)
2. **Batch dbt updates** (update once per day, then refresh app once)
3. **Don't refresh unnecessarily** (only when dbt models actually change)
4. **15-minute cache** provides backup freshness without excessive queries

---

## Best Practices

### ✅ DO:

1. **Refresh after dbt updates**: Always click "Refresh Data" after `dbt build`
2. **Daily refreshes as season approaches**: More frequent updates closer to season start
3. **Verify rankings updated**: Check a few player values after refresh
4. **Update during draft windows**: Refresh between pick clocks (not mid-decision)

### ❌ DON'T:

1. **Don't refresh unnecessarily**: Only refresh when dbt models actually update
2. **Don't rely solely on auto-refresh**: Manual refresh ensures you get latest data immediately
3. **Don't refresh during active pick clock**: Wait until you have time to review changes
4. **Don't forget to rebuild dbt first**: Refresh button won't help if dbt models aren't updated

---

## Troubleshooting

### Rankings Don't Seem Updated

**Check:**
1. Did you run `dbt build --select mart_*` successfully?
2. Did you click "Refresh Data" button after dbt update?
3. Are you looking at the correct format (50s vs OC)?
4. Wait a moment - query may still be running (check spinner)

**Solution:**
- Verify dbt models built successfully: `dbt run --select mart_*`
- Click refresh button again (may need to wait for previous query)
- Check Athena directly to verify data updated

### Cache Not Refreshing

**Symptoms:**
- Refresh button clicked but data doesn't change
- Rankings seem stale

**Solution:**
- Verify cache_version is updating (check Streamlit session state)
- Wait for previous query to complete before clicking again
- Try switching to different draft then back
- Restart Streamlit app if persistent issues

### High Costs

**If you notice costs rising:**
1. Check how often you're clicking refresh (should be ~once per day)
2. Verify 15-minute cache is working (check timestamps)
3. Consider reducing refresh frequency if earlier in preseason
4. Use manual refresh only, not auto-refresh every 15 minutes

---

## Technical Details

### Cache Version Mechanism

**How it works:**
```python
# Initial cache version (set on app load)
st.session_state.cache_version = datetime.now().strftime('%Y%m%d_%H%M%S')

# When refresh button clicked
st.session_state.cache_version = datetime.now().strftime('%Y%m%d_%H%M%S')  # New timestamp

# Query function includes cache_version in cache key
@st.cache_data(ttl=900)
def query_mart_table(..., cache_version: Optional[str] = None):
    # Different cache_version = different cache entry = cache miss
```

**Why this works:**
- Streamlit uses all function parameters as part of cache key
- Changing `cache_version` creates new cache key
- New cache key = cache miss = fresh query from Athena
- Old cache entry remains until TTL expires (but isn't used)

### Cache TTL (15 Minutes)

**Rationale:**
- Balances freshness with cost efficiency
- Supports daily refreshes without excessive queries
- Auto-refresh provides backup if manual refresh forgotten
- Still 95%+ cost savings vs no caching

**Alternative TTL Options:**
- **30 minutes**: Lower costs, less frequent auto-refresh
- **10 minutes**: More frequent auto-refresh, slightly higher costs
- **No TTL**: Manual refresh only, maximum control

---

## Summary

**For Daily dbt Refreshes During Slow Drafts:**

1. ✅ **Update dbt models daily** as season approaches
2. ✅ **Click "Refresh Data" button** after each dbt update
3. ✅ **Verify rankings updated** before making draft decisions
4. ✅ **Use 15-minute cache** as backup (auto-refreshes if you forget)
5. ✅ **Cost remains minimal** (~$0.01 per draft even with daily refreshes)

**Key Takeaway:**
The app is optimized for daily dbt refreshes with manual refresh capability, 15-minute auto-refresh backup, and minimal cost impact. Perfect for keeping rankings current as projections evolve closer to the season!
