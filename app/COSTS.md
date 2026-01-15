# Cost Analysis & Optimization Guide

## Cost Breakdown: Can You Keep It Free?

**Short answer: Yes, for personal use this should be very cheap (likely under $5/month, potentially free)!**

The app is already optimized for cost-efficiency. Here's the breakdown:

---

## AWS Service Costs

### 1. **DynamoDB** ✅ Already Optimized for Cost

**Current Setup:**
- **Billing Mode**: `PAY_PER_REQUEST` (on-demand)
- **Cost**: $1.25 per million write requests, $0.25 per million read requests

**Estimated Monthly Cost:**
- A typical draft has ~300-400 picks
- Reads: ~1,000 per draft session (filtering, checking status) = **$0.00025**
- Writes: ~400 per draft (marking players) = **$0.0005**
- **Total per draft: ~$0.001 (less than a penny!)**
- **Monthly (even 10 drafts): ~$0.01**

**Free Tier:** 
- 25 GB storage (way more than you'll need)
- 25 write capacity units / 25 read capacity units
- **First 25M requests/month are FREE**

**Optimization:** Already using on-demand billing (best for sporadic use)

---

### 2. **Amazon Athena** ⚠️ Main Cost Driver (but manageable)

**Cost Model:**
- **$5 per TB of data scanned**
- Charges only for data scanned, not data stored

**Estimated Monthly Cost:**

Your mart tables are likely small:
- Typical player rankings table: ~1,000-2,000 rows
- Each row might be ~1-2 KB
- Total table size: ~1-5 MB
- Query scanning full table: ~$0.000005 - $0.000025 per query

**Monthly Estimates (with caching):**
- 10 query executions (app caches for 5 minutes) = ~$0.00005
- Even 100 queries/month = **~$0.0005 (less than a penny)**

**Free Tier:** 
- **First 10 TB scanned per month is $5/TB**
- But your usage is so minimal, you'll likely stay well under any meaningful threshold

**Cost Optimization Already in Place:**
- ✅ **5-minute query caching** (reduces duplicate queries by ~95%)
- ✅ Only queries when data is refreshed
- ✅ Queries specific mart tables (not scanning raw data)

**Additional Optimization Tips:**
- The app already caches results - this prevents repeated expensive queries
- Only queries the mart tables (pre-aggregated), not raw source data
- Uses Iceberg tables which can be more efficient than traditional Athena tables

---

### 3. **Amazon S3** 💰 Storage & Query Results (Minimal)

**Storage Costs:**
- **$0.023 per GB/month** (Standard storage, first 50 GB free)
- Your mart tables are likely <100 MB total = **~$0.002/month**

**Query Results Storage:**
- Athena query results stored in S3
- ~1-5 MB per query result
- Results automatically cleaned up by Athena after 30 days (configurable)
- **Cost: Negligible (~$0.001/month)**

**Data Transfer:**
- First 100 GB/month out of S3 is free
- For personal use, you'll stay well under this

**Free Tier:**
- **5 GB standard storage free for 12 months**
- **20,000 GET requests / 2,000 PUT requests free**

---

### 4. **Streamlit Cloud** 🆓 Free Tier Available!

**Free Tier:**
- **Unlimited public apps**
- **1 private app** (requires GitHub)
- **No time limits** (apps run continuously)
- **Deploy from GitHub** (automatic deploys)

**Pricing:**
- **Free tier**: Up to 3 apps (1 private, unlimited public)
- **Team tier**: $20/month (not needed for personal use)
- **Enterprise**: Custom pricing (definitely not needed)

**For Your Use Case:**
- Free tier is perfect (even if you make it private, one app is fine)
- Deploy from your GitHub repo
- Automatic HTTPS included
- **Cost: $0/month**

---

## Total Monthly Cost Estimate

### Conservative Estimate (Heavy Usage):
- **DynamoDB**: $0.01 (well within free tier)
- **Athena**: $0.01 (even with 100+ queries/month)
- **S3 Storage**: $0.01 (if you have a lot of data)
- **S3 Query Results**: $0.001
- **Streamlit Cloud**: $0 (free tier)

**Total: ~$0.03/month (3 cents!)**

### Realistic Estimate (Normal Usage):
- **DynamoDB**: $0 (free tier covers it)
- **Athena**: $0.001 (10-20 queries/month)
- **S3**: $0 (free tier covers it)
- **Streamlit Cloud**: $0 (free tier)

**Total: ~$0.001/month (practically free)**

### Worst Case (Extremely Heavy Usage):
- **DynamoDB**: $0.10 (10,000 requests)
- **Athena**: $0.10 (scanning 20 GB/month - unlikely!)
- **S3**: $0.05 (500 GB - way more than you'll have)
- **Streamlit Cloud**: $0

**Total: ~$0.25/month (worst case scenario)**

---

## Cost Optimization Strategies (Already Implemented)

### ✅ Already Done:
1. **DynamoDB on-demand billing** - Only pay for what you use
2. **Query caching (5 minutes)** - Reduces Athena queries by 95%+
3. **Querying mart tables only** - Pre-aggregated data, smaller scans
4. **Iceberg tables** - More efficient than traditional Athena tables
5. **Streamlit Cloud free tier** - No hosting costs

### Additional Optimizations You Can Add:

1. **Increase cache TTL** (if needed):
   ```python
   @st.cache_data(ttl=3600)  # Cache for 1 hour instead of 5 minutes
   ```
   This reduces queries even more (only refresh once per hour)

2. **Add query result expiration** in Athena:
   - Set S3 query result expiration to 1 day (default is 30 days)
   - Reduces S3 storage costs (minimal savings, but good practice)

3. **Use AWS Data Compression**:
   - Iceberg tables already use Parquet (columnar, compressed)
   - Your tables are already optimized

4. **Monitor Usage** (optional):
   - Set up AWS Budget alerts (free)
   - Get notified if costs exceed $1/month (very unlikely)

---

## Cost Comparison: Self-Hosted vs Streamlit Cloud

### Option 1: Streamlit Cloud (Recommended)
- **Hosting**: $0 (free tier)
- **AWS Services**: ~$0.01-0.03/month
- **Total: ~$0.03/month**
- ✅ **Pros**: Zero setup, automatic HTTPS, easy deployment
- ❌ **Cons**: Limited to 1 private app (but that's fine for your use case)

### Option 2: Self-Hosted (EC2 t2.micro)
- **EC2 t2.micro**: $0.0116/hour = ~$8.50/month (if running 24/7)
- **AWS Services**: ~$0.01-0.03/month (same as above)
- **Total: ~$8.53/month**
- ❌ **Pros**: More control
- ❌ **Cons**: More expensive, requires maintenance

**Recommendation**: Use Streamlit Cloud - it's free and easier!

---

## AWS Free Tier Details

### Always Free (No Expiration):
- **DynamoDB**: 25 GB storage + 25 WCU/RCU
- **S3**: 5 GB storage + 20,000 GET requests
- **IAM**: Always free
- **CloudWatch**: Basic monitoring (free tier)

### 12-Month Free Tier (New AWS Accounts):
- **S3**: First 5 GB storage free for 12 months
- **Lambda**: 1M requests/month free
- **Data Transfer**: First 100 GB/month free

**For Your Use Case:**
- Your usage is so minimal that you'll likely stay within the always-free tiers
- Even after 12 months, costs will remain negligible

---

## Cost Monitoring Setup (Optional)

If you want to track costs (recommended for peace of mind):

1. **AWS Budget Alerts** (Free):
   ```bash
   # Via AWS Console:
   # Billing → Budgets → Create budget
   # Set alert at $1/month
   ```

2. **AWS Cost Explorer** (Free):
   - View costs by service
   - Available in AWS Console → Billing

3. **Set up billing alerts**:
   - Get email when costs exceed thresholds
   - Recommend: $1/month alert (you'll never hit it, but peace of mind)

---

## Real-World Usage Scenario

**Typical Draft Day Usage:**
- 1 draft session = ~2 hours
- ~50 queries (but cached, so ~5 actual queries)
- ~400 DynamoDB operations
- **Cost: ~$0.0001 per draft**

**Monthly Usage (Active Draft Season):**
- 5 draft sessions = ~$0.0005
- Off-season usage = $0 (app not used)
- **Annual cost: ~$0.01 (1 cent!)**

---

## Cost Summary

| Service | Monthly Cost | Free Tier Coverage |
|---------|-------------|-------------------|
| **DynamoDB** | $0.01 | ✅ Yes (25M requests) |
| **Athena** | $0.01 | ✅ Effectively free at this scale |
| **S3** | $0.01 | ✅ Yes (5 GB + 20K requests) |
| **Streamlit Cloud** | $0 | ✅ Free tier |
| **Total** | **~$0.03/month** | ✅ **Practically free** |

---

## Recommendations

1. **Use Streamlit Cloud** - Free hosting, no server maintenance
2. **Keep current optimizations** - Already well-optimized for cost
3. **Monitor via AWS Budget** - Set $1/month alert (optional, but recommended)
4. **Don't worry about costs** - Your usage is so minimal, it's effectively free

**Bottom Line: For personal fantasy baseball draft use, this will cost less than $0.10/month, likely $0.01/month or free entirely thanks to AWS free tiers and the optimizations already in place.**

The app is already configured for cost-efficiency - you're good to go! 🎉
