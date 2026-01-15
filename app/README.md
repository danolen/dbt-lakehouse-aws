# Fantasy Baseball Draft Tool - Streamlit App

This Streamlit application provides an interactive interface for fantasy baseball draft preparation and tracking.

## Features

- 📊 View player rankings from your dbt mart models (50s and OC formats)
- 🔍 Filter players by position, team, and draft status
- ✅ Track which players have been drafted using DynamoDB
- 📱 Mobile and desktop-friendly interface
- 🎯 Real-time filtering and sorting
- 🐌 **Optimized for slow drafts** (2-4 hour pick clocks, days/weeks long)
- 🔄 **Multiple concurrent drafts** support (same or different formats)
- 📈 **Automatic progress tracking** (round, pick number, completion %)
- 💾 **Long-term persistence** (draft state saved across sessions)

## Setup Instructions

### Prerequisites

1. **Python 3.8 or higher** installed on your system
2. **AWS CLI** configured with appropriate credentials
3. **dbt models built** - Ensure your mart models are up-to-date in Athena

### Step 1: Configure AWS Credentials

You have two options:

**Option A: Using AWS CLI (Recommended)**
```bash
aws configure
```
You'll be prompted for:
- AWS Access Key ID
- AWS Secret Access Key
- Default region (e.g., `us-east-1`)
- Default output format (can leave as default)

**Option B: Environment Variables**
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

### Step 2: Set Up Python Virtual Environment

From the project root directory:

```bash
# Make setup script executable (macOS/Linux)
chmod +x setup.sh

# Run setup script
./setup.sh
```

Or manually:

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configure Athena Settings (if needed)

The app uses environment variables for configuration (or Streamlit Secrets for remote deployment).
See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options and remote access setup.

**Quick setup (local development):**

You can override defaults with environment variables:

```bash
export ATHENA_DATABASE=your_database
export ATHENA_SCHEMA=your_schema
export ATHENA_S3_OUTPUT_LOCATION=s3://your-bucket/query-results/
export AWS_DEFAULT_REGION=us-east-1
```

**Default values:**
- `ATHENA_DATABASE`: `AwsDataCatalog` (default for external tables)
- `ATHENA_SCHEMA`: `main` (where your mart tables are)
- `ATHENA_S3_OUTPUT_LOCATION`: (must be configured - no default)
- `ATHENA_REGION`: `us-east-1`

**Note**: For remote access (Streamlit Cloud, EC2, etc.), see [CONFIGURATION.md](CONFIGURATION.md) for deployment-specific instructions.

### Step 4: Ensure dbt Models Are Built

Before running the app, make sure your mart models are built in Athena:

```bash
# Build all models
dbt build

# Or just build mart models
dbt build --select mart_*
```

### Step 5: Run the Streamlit App

With your virtual environment activated:

```bash
streamlit run app/app.py
```

The app will open in your default web browser, typically at `http://localhost:8501`

## Cost Considerations

**Good news: This app is already optimized for cost-efficiency!**

For personal use, expect costs of **~$0.01-0.03/month** (practically free):

- ✅ **DynamoDB**: Using on-demand billing (pay per request) - well within free tier
- ✅ **Athena**: 5-minute query caching reduces queries by 95%+
- ✅ **S3**: Well within free tier (5 GB + 20K requests)
- ✅ **Streamlit Cloud**: Free tier available (unlimited public apps, 1 private app)

**See [COSTS.md](COSTS.md) for detailed cost breakdown and optimization strategies.**

## Usage

### Starting a Draft Session

**For Slow Drafts (Recommended Approach):**

1. **Create New Draft**: Click "➕ Create New Draft" in the sidebar
   - Enter draft name/description (e.g., "Main 50s League 2024")
   - Select format (50s or OC)
   - Set number of teams (default: 12)
   - Set number of rounds (default: 50)
   - Set pick clock in hours (default: 4 hours)
   - Click "Create Draft"

2. **Draft is automatically registered** and tracked with metadata
   - Progress (round, pick number) automatically calculated
   - Draft persists across sessions (days/weeks for slow drafts)
   - Each draft gets its own DynamoDB table

### Managing Multiple Drafts

**Switch Between Drafts:**
- Use "🔄 Switch Draft" dropdown in sidebar
- Shows all active drafts with progress information
- Click "Switch to This Draft" to view/edit

**Multiple Concurrent Drafts:**
- Create as many drafts as needed (same or different formats)
- Each draft is independent with its own tracking
- Switch between drafts anytime to manage multiple leagues simultaneously

**Draft Registry:**
- All drafts are tracked in a central registry table
- See draft status, progress, and metadata
- Completed drafts can be archived (marked as completed)

### Filtering Players

Use the sidebar filters to:
- Filter by position group (e.g., OF, 1B, P)
- Filter by team
- Show/hide drafted players

### Marking Players as Drafted

1. Use the player selector dropdown at the bottom of the page
2. Click "✅ Mark as Drafted (Auto Pick #)" to mark a player
   - **Pick number is automatically assigned** (next available pick)
   - **Progress is automatically updated** (round, pick number, completion %)
   - Supports **snake draft** format (reverse order every other round)
3. Click "❌ Mark as Undrafted" to undo
   - Progress is automatically recalculated

**For Slow Drafts:**
- Pick numbers auto-increment (1, 2, 3, ...)
- Round number calculated automatically based on pick and number of teams
- Draft can span days/weeks - state persists across sessions
- **Data cached for 15 minutes** (auto-refreshes; manual refresh available after dbt updates)

### Draft Management

- **Refresh Data (After dbt Update)**: Forces immediate refresh from Athena (bypasses cache)
  - **Use this after updating dbt models** to get latest rankings
  - Cache automatically refreshes every 15 minutes otherwise
  - Supports daily dbt model refreshes as season approaches
- **Clear This Draft**: Removes all picks from current draft (resets to beginning)
- **Complete Draft**: Marks draft as completed (archives it)
- **Draft Summary**: Shows round, pick number, progress %, teams, rounds, pick clock

**Recommended Workflow for Daily Updates:**
1. Update dbt models: `dbt build --select mart_*`
2. Click "🔄 Refresh Data" button in app
3. Fresh rankings load immediately (bypasses 15-minute cache)

**Draft Progress Tracking:**
- **Current Round**: Automatically calculated (e.g., "Round 5 of 50")
- **Picks Completed**: Shows picks made vs total picks
- **Next Pick**: Next available pick number
- **Progress %**: Visual progress bar showing draft completion
- **Status**: Active, Completed, etc.

## DynamoDB Tables

The app automatically creates DynamoDB tables:

**Draft Tracking Tables:**
- Naming pattern: `fantasy_baseball_draft_{draft_id}`
- **Partition Key**: `player_id` (String) - matches the `id` field from your mart models
- Stores: Player ID, draft pick number, drafted timestamp, player name

**Draft Registry Table:**
- Name: `fantasy_baseball_draft_registry`
- **Partition Key**: `draft_id` (String)
- Stores: Draft metadata (format, teams, rounds, pick clock, progress, status, etc.)

Tables are created with **on-demand billing** (PAY_PER_REQUEST), making them cost-efficient for personal use. Perfect for slow drafts that span days/weeks.

## Troubleshooting

### "AWS credentials not configured" error

- Verify AWS CLI is configured: `aws sts get-caller-identity`
- Check environment variables are set correctly
- Ensure IAM credentials have permissions for Athena and DynamoDB

### "Error querying database" or table not found

- Ensure your dbt models have been built: `dbt build --select mart_*`
- Verify table names match in `app/config/aws_config.py`
- Check that schema name matches your dbt configuration
- Verify IAM permissions allow Athena queries

### DynamoDB errors

- Check IAM permissions include DynamoDB access
- Verify region matches your AWS configuration
- Check that table creation permissions are granted

## IAM Permissions Required

Your AWS credentials need the following permissions:

**Athena:**
- `athena:StartQueryExecution`
- `athena:GetQueryExecution`
- `athena:GetQueryResults`
- `athena:GetWorkGroup` (if using work groups)
- `glue:GetDatabase`
- `glue:GetTable`
- `s3:GetObject` (for query results)
- `s3:PutObject` (for query results)

**DynamoDB:**
- `dynamodb:CreateTable`
- `dynamodb:DescribeTable`
- `dynamodb:PutItem`
- `dynamodb:GetItem`
- `dynamodb:DeleteItem`
- `dynamodb:Scan`

## Project Structure

```
app/
├── app.py                 # Main Streamlit application
├── config/
│   └── aws_config.py     # AWS configuration and connection settings
├── utils/
│   ├── database.py       # Athena query utilities
│   └── dynamodb.py       # DynamoDB draft tracking utilities
└── README.md             # This file
```

## Cost Optimization

The app is already optimized for minimal costs:

1. **Query Caching**: Results cached for 5 minutes (reduces Athena queries by ~95%)
2. **DynamoDB On-Demand**: Only pay for actual requests (well within free tier)
3. **Efficient Queries**: Only queries pre-aggregated mart tables, not raw data
4. **Streamlit Cloud Free Tier**: No hosting costs

**Estimated Monthly Cost: ~$0.01-0.03** (practically free for personal use)

See [COSTS.md](COSTS.md) for detailed cost analysis and optimization strategies.

## Future Enhancements

- [ ] Export draft list to CSV
- [ ] Undo last draft pick functionality
- [ ] Draft position/round tracker
- [ ] Position scarcity indicators
- [ ] Value vs ADP visualizations
- [ ] Multi-user draft support
- [ ] Draft pick history timeline
- [ ] Option to increase cache TTL for even lower costs (if data doesn't change often)
