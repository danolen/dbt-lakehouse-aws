# Configuration Guide

## Two Ways to Set Configuration

### Option 1: .env File (Recommended for Local Development)

1. **Copy the example file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your values:**
   ```bash
   ATHENA_DATABASE=AwsDataCatalog
   ATHENA_SCHEMA=dbt_main
   ATHENA_REGION=us-east-1
   ATHENA_S3_OUTPUT=s3://your-bucket/query-results/
   ```

3. **The app automatically loads `.env`** - no extra steps needed!

**Why this is good:**
- ✅ Easy to manage
- ✅ `.env` is ignored by git (your secrets stay private)
- ✅ Different values for different environments
- ✅ No need to set system environment variables

### Option 2: Environment Variables

Set them in your terminal before running the app:

**macOS/Linux:**
```bash
export ATHENA_DATABASE=AwsDataCatalog
export ATHENA_SCHEMA=dbt_main
export ATHENA_REGION=us-east-1
export ATHENA_S3_OUTPUT=s3://your-bucket/query-results/
streamlit run app/app.py
```

**Windows (PowerShell):**
```powershell
$env:ATHENA_DATABASE="AwsDataCatalog"
$env:ATHENA_SCHEMA="dbt_main"
$env:ATHENA_REGION="us-east-1"
$env:ATHENA_S3_OUTPUT="s3://your-bucket/query-results/"
streamlit run app/app.py
```

## AWS Credentials

AWS credentials are handled separately by boto3 (which pyathena uses). They come from:

1. **AWS CLI** (recommended):
   ```bash
   aws configure
   ```
   This sets credentials in `~/.aws/credentials`

2. **Environment variables:**
   ```bash
   export AWS_ACCESS_KEY_ID=your_key
   export AWS_SECRET_ACCESS_KEY=your_secret
   export AWS_DEFAULT_REGION=us-east-1
   ```

3. **IAM roles** (if running on EC2/ECS)

## How It Works

The app uses `os.getenv()` to read environment variables:

```python
ATHENA_SCHEMA = os.getenv("ATHENA_SCHEMA", "dbt_main")
```

This means:
- If `ATHENA_SCHEMA` environment variable exists → use that value
- If not → use the default `"dbt_main"`

The `python-dotenv` library automatically loads `.env` files, so you don't need to do anything special - just create the file!

## Priority Order

1. **Environment variables** (set in terminal/system)
2. **`.env` file** (loaded by python-dotenv)
3. **Default values** (hardcoded in the script)

This gives you flexibility - you can override defaults easily without changing code.
