# Configuration Guide - Remote Access & Deployment

## Why Environment Variables?

I chose environment variables (with Streamlit Secrets support) for configuration because:

1. **Flexibility**: Override defaults without changing code
2. **Security**: Don't hardcode sensitive values in version control
3. **Deployment-friendly**: Works across different environments (local, cloud, containers)
4. **Standard Practice**: Industry-standard way to configure applications
5. **Remote Access Support**: Works perfectly for remote deployments - just set env vars in your deployment environment

## Configuration Priority

The app reads configuration in this order (first available wins):

1. **Streamlit Secrets** (for Streamlit Cloud deployment) - `st.secrets['aws']['key']`
2. **Environment Variables** (for local or self-hosted) - `os.getenv('KEY')`
3. **Hardcoded Defaults** (for local development convenience)

## Remote Access - Will This Work?

**Yes!** Environment variables work perfectly for remote access. Here's how:

### Option 1: Streamlit Cloud (Recommended for Remote Access)

**Best for**: Easy deployment, automatic HTTPS, free tier available

1. Push your code to GitHub
2. Connect to Streamlit Cloud
3. Configure secrets via Streamlit Cloud UI:
   - Go to your app settings
   - Click "Secrets"
   - Add configuration in TOML format:

```toml
[aws]
athena_database = "AwsDataCatalog"
athena_schema = "main"
athena_s3_output_location = "s3://your-bucket/query-results/"
aws_region = "us-east-1"

# AWS Credentials (or use IAM role)
aws_access_key_id = "your_access_key"
aws_secret_access_key = "your_secret_key"
```

**Note**: Streamlit Cloud secrets are encrypted and only accessible to your app.

### Option 2: Self-Hosted (EC2, ECS, Your Server)

**Best for**: Full control, can use IAM roles

#### Using Environment Variables:

Set environment variables on your server:

```bash
export ATHENA_DATABASE=AwsDataCatalog
export ATHENA_SCHEMA=main
export ATHENA_S3_OUTPUT_LOCATION=s3://your-bucket/query-results/
export AWS_DEFAULT_REGION=us-east-1

# AWS Credentials (or use IAM role - RECOMMENDED)
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
```

#### Using IAM Roles (Best for AWS-hosted):

If running on EC2 or ECS, use IAM roles instead of credentials:
- Create an IAM role with required permissions
- Attach role to EC2 instance or ECS task
- No credentials needed - boto3 automatically uses the role
- More secure than storing credentials

### Option 3: Docker Container

**Best for**: Consistent deployment across environments

Create a `.env` file (or use Docker secrets):

```bash
ATHENA_DATABASE=AwsDataCatalog
ATHENA_SCHEMA=main
ATHENA_S3_OUTPUT_LOCATION=s3://your-bucket/query-results/
AWS_DEFAULT_REGION=us-east-1
```

Run with:
```bash
docker run --env-file .env your-streamlit-app
```

Or use Docker secrets for sensitive values.

## Configuration Options

### Required Configuration

| Environment Variable | Streamlit Secret | Default | Description |
|---------------------|------------------|---------|-------------|
| `ATHENA_S3_OUTPUT_LOCATION` | `aws.athena_s3_output_location` | (none - **must be set**) | S3 bucket for Athena query results |
| AWS Credentials | `aws.aws_access_key_id` / `aws.aws_secret_access_key` | (from AWS CLI/config) | AWS credentials (or use IAM role) |

### Optional Configuration

| Environment Variable | Streamlit Secret | Default | Description |
|---------------------|------------------|---------|-------------|
| `ATHENA_DATABASE` | `aws.athena_database` | `AwsDataCatalog` | Athena database name |
| `ATHENA_SCHEMA` | `aws.athena_schema` | `main` | Schema where mart tables are |
| `AWS_DEFAULT_REGION` | `aws.aws_region` | `us-east-1` | AWS region |
| `AWS_REGION` | (same as above) | `us-east-1` | Alternative region env var |

## Setting Up for Remote Access

### For Streamlit Cloud:

1. **Set up secrets** in Streamlit Cloud UI (see Option 1 above)
2. **Ensure AWS credentials** have permissions for:
   - Athena: Query execution, Glue catalog access
   - DynamoDB: Table creation, read/write access
   - S3: Read/write to query results bucket

### For Self-Hosted:

1. **Set environment variables** on your server (see Option 2 above)
2. **OR use IAM roles** if running on AWS (more secure)
3. **Configure systemd/PM2/supervisor** to run Streamlit with environment variables:
   ```bash
   # Example systemd service file
   [Service]
   Environment="ATHENA_DATABASE=AwsDataCatalog"
   Environment="ATHENA_SCHEMA=main"
   Environment="ATHENA_S3_OUTPUT_LOCATION=s3://your-bucket/query-results/"
   Environment="AWS_DEFAULT_REGION=us-east-1"
   ```

### Security Best Practices

1. **Never commit credentials** to version control
2. **Use IAM roles** when running on AWS (instead of access keys)
3. **Use secrets management** (Streamlit Secrets, AWS Secrets Manager, etc.)
4. **Limit permissions** to only what's needed (principle of least privilege)
5. **Rotate credentials** regularly

## Testing Remote Configuration

To test that configuration is working:

```bash
# Check environment variables are set
echo $ATHENA_DATABASE
echo $ATHENA_SCHEMA

# Verify AWS credentials
aws sts get-caller-identity

# Test Streamlit app
streamlit run app/app.py
```

## Troubleshooting Remote Access

### "AWS credentials not configured"

- **Streamlit Cloud**: Check that secrets are set correctly in the UI
- **Self-hosted**: Verify environment variables are set and accessible to the Streamlit process
- **IAM Role**: Ensure role is attached and has correct permissions

### "Error querying database"

- Check `ATHENA_DATABASE` and `ATHENA_SCHEMA` match your dbt configuration
- Verify `ATHENA_S3_OUTPUT_LOCATION` is set and accessible
- Ensure IAM permissions include Athena and Glue access

### "Table not found"

- Verify your dbt models are built: `dbt build --select mart_*`
- Check schema name matches between dbt and app configuration
- Verify table names match (they're hardcoded in `aws_config.py`)

## Example: Full Remote Setup (Streamlit Cloud)

1. **GitHub Setup**:
   ```bash
   git push origin main
   ```

2. **Streamlit Cloud Setup**:
   - Connect GitHub repo to Streamlit Cloud
   - Configure secrets (see Option 1 above)
   - Deploy!

3. **Access Anywhere**:
   - Streamlit Cloud provides HTTPS URL
   - Accessible from any device
   - No VPN or port forwarding needed

## Summary

**Environment variables are NOT a problem for remote access** - they're actually the **recommended approach**! Just set them in your deployment environment (Streamlit Cloud secrets, server environment, Docker env file, etc.). The app will automatically pick them up.

The key advantage is that you can:
- **Develop locally** with AWS CLI credentials (no config needed)
- **Deploy remotely** with environment variables or secrets
- **Switch environments** without changing code
