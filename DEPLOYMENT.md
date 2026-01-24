# Deployment Guide for Streamlit Community Cloud

This guide will help you deploy your Fantasy Baseball Draft Tool to Streamlit Community Cloud.

## Prerequisites

1. **GitHub Account**: Your code needs to be in a GitHub repository
2. **Streamlit Account**: Sign up at [share.streamlit.io](https://share.streamlit.io)
3. **AWS Credentials**: You'll need AWS access keys with permissions for:
   - Amazon Athena (read queries)
   - Amazon S3 (read query results)
   - Amazon DynamoDB (read/write for draft tracking)

## Step 1: Prepare Your Repository

Your repository structure should look like this:
```
dbt-lakehouse-aws/
├── app/
│   └── app.py          # Main app file
├── requirements.txt    # Python dependencies (must be at root)
└── streamlit_app.py    # Entry point for Streamlit Cloud (optional)
```

The `streamlit_app.py` file at the root is a simple wrapper that imports your app. This makes it easier for Streamlit Cloud to find your app.

## Step 2: Configure Streamlit Secrets

Streamlit Cloud uses **Secrets** instead of `.env` files. You'll configure these in the Streamlit Cloud dashboard.

1. **Go to your app settings** in Streamlit Cloud
2. **Click "Secrets"** in the sidebar
3. **Add your configuration** in TOML format:

```toml
[default]
# Athena Configuration
ATHENA_DATABASE = "AwsDataCatalog"
ATHENA_SCHEMA = "dbt_main"
ATHENA_REGION = "us-east-1"
ATHENA_S3_OUTPUT = "s3://your-bucket/query-results/"

# DynamoDB Configuration
DYNAMODB_REGION = "us-east-1"
DYNAMODB_TABLE_NAME = "fantasy_baseball_draft"

# AWS Credentials (REQUIRED for Streamlit Cloud)
AWS_ACCESS_KEY_ID = "your-access-key-id"
AWS_SECRET_ACCESS_KEY = "your-secret-access-key"
AWS_DEFAULT_REGION = "us-east-1"
```

**Important:** AWS credentials are **required** for Streamlit Cloud deployment. The app needs these to connect to Athena, S3, and DynamoDB.

### Alternative: IAM Role (Advanced)

If you're running on AWS infrastructure, you can use IAM roles instead of access keys, but this is not available on Streamlit Cloud.

**Option 2: IAM Role (Advanced)**
If you're running on AWS infrastructure, you can use IAM roles instead of access keys.

## Step 3: Deploy to Streamlit Cloud

1. **Go to [share.streamlit.io](https://share.streamlit.io)**
2. **Click "New app"**
3. **Connect your GitHub repository**
4. **Configure your app:**
   - **Repository**: Select your `dbt-lakehouse-aws` repo
   - **Branch**: `main` (or your default branch)
   - **Main file path**: `streamlit_app.py` (or `app/app.py` if you didn't create the wrapper)
   - **App URL**: Choose a custom subdomain (e.g., `fantasy-baseball-draft`)
5. **Click "Deploy"**

## Step 4: Verify Deployment

After deployment, check:
- ✅ App loads without errors
- ✅ Can connect to Athena (test by clicking "Load Player Rankings")
- ✅ DynamoDB operations work (test by marking a player as drafted)
- ✅ All filters and features work correctly

## Troubleshooting

### "Configuration Error: ATHENA_S3_OUTPUT is required"
- Make sure you've added `ATHENA_S3_OUTPUT` to your Streamlit Secrets
- Check that the TOML format is correct (no quotes needed for strings)

### "Access Denied" or AWS Authentication Errors
- Verify your AWS credentials in Streamlit Secrets
- Check that your AWS IAM user has the necessary permissions:
  - `athena:StartQueryExecution`
  - `athena:GetQueryExecution`
  - `athena:GetQueryResults`
  - `s3:GetObject` (for the S3 output bucket)
  - `dynamodb:*` (for draft tracking)

### "Module not found" errors
- Check that `requirements.txt` includes all dependencies
- Verify the file is at the repository root (not in `app/`)

### App can't find the entry point
- If using `streamlit_app.py`, make sure it's at the repository root
- Or configure the "Main file path" in Streamlit Cloud settings to point to `app/app.py`

## Security Best Practices

1. **Never commit secrets to Git**: Your `.env` file should be in `.gitignore` (it already is)
2. **Use IAM roles when possible**: More secure than access keys
3. **Limit AWS permissions**: Only grant the minimum permissions needed
4. **Rotate credentials regularly**: Update Streamlit Secrets periodically

## Cost Considerations

- **Streamlit Cloud**: Free tier available (with some limitations)
- **AWS Athena**: Pay per query (~$5 per TB scanned)
- **AWS DynamoDB**: Free tier includes 25GB storage and 25 read/write units
- **AWS S3**: Very cheap for storing query results

## Updating Your App

After making changes:
1. Push changes to your GitHub repository
2. Streamlit Cloud will automatically redeploy
3. Or manually trigger a redeploy from the Streamlit Cloud dashboard

## Local Development vs Cloud

The app supports both:
- **Local**: Uses `.env` file (via `python-dotenv`)
- **Cloud**: Uses Streamlit Secrets (via `st.secrets`)

The app automatically detects which environment it's running in and uses the appropriate configuration method.
