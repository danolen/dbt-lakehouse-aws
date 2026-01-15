"""
AWS Configuration for Draft Tool

This module handles AWS configuration including Athena and DynamoDB settings.
Supports multiple configuration sources (in order of priority):
1. Streamlit Secrets (for Streamlit Cloud deployment)
2. Environment variables (for local development or self-hosted)
3. Hardcoded defaults (for local development convenience)

AWS Credentials (for boto3) can come from:
- Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
- AWS credentials file (~/.aws/credentials) - when running locally
- IAM role (when running on EC2/ECS/Lambda) - BEST for production
- Streamlit secrets (for Streamlit Cloud)

Configuration priority (first available wins):
1. Streamlit secrets (if running in Streamlit Cloud)
2. Environment variables
3. Hardcoded defaults (for local development)

WHY ENVIRONMENT VARIABLES:
- Flexibility: Override defaults without changing code
- Security: Don't hardcode sensitive values in version control
- Deployment-friendly: Works across different environments (local, cloud, containers)
- Standard practice: Industry-standard way to configure applications

REMOTE ACCESS CONSIDERATIONS:
- Environment variables work fine for remote access - just set them in your deployment environment
- For Streamlit Cloud: Use Streamlit Secrets Management (secrets.toml)
- For self-hosted (EC2/ECS): Set environment variables on the server
- For AWS-hosted: Use IAM roles (no credentials needed) or environment variables
"""

import os
from typing import Optional
import boto3


def _get_config_value(key: str, default: str) -> str:
    """
    Get configuration value from multiple sources (priority order):
    1. Streamlit secrets (if available and Streamlit is running)
    2. Environment variables
    3. Default value
    
    This function is called dynamically when config values are accessed,
    allowing Streamlit secrets to work even though they're not available at import time.
    """
    # Try Streamlit secrets first (only works when Streamlit is running)
    try:
        import streamlit as st
        # Check if we're in a Streamlit context and secrets exist
        if hasattr(st, 'secrets') and st.secrets:
            try:
                aws_secrets = st.secrets.get('aws', {})
                if isinstance(aws_secrets, dict) and key.lower() in aws_secrets:
                    value = aws_secrets[key.lower()]
                    if value:  # Only return if not empty
                        return str(value)
            except (AttributeError, TypeError):
                pass
    except ImportError:
        pass
    except Exception:
        # If Streamlit isn't available or not running, continue to env vars
        pass
    
    # Fall back to environment variables
    env_key = key.upper()
    env_value = os.getenv(env_key, default)
    return env_value if env_value else default


class AWSConfig:
    """Configuration class for AWS services"""
    
    # Configuration defaults (used if not set via env vars or secrets)
    _DEFAULTS = {
        "ATHENA_DATABASE": "AwsDataCatalog",
        "ATHENA_SCHEMA": "main",
        "ATHENA_S3_OUTPUT_LOCATION": "",  # Must be configured - no default
        "ATHENA_REGION": "us-east-1",
        "DYNAMODB_REGION": "us-east-1",
    }
    
    # Cache for computed values (lazy evaluation)
    _cache = {}
    
    # Static values (don't need configuration)
    DYNAMODB_TABLE_PREFIX = "fantasy_baseball_draft"
    MART_TABLE_50S = "mart_preseason_overall_rankings_50s"
    MART_TABLE_OC = "mart_preseason_overall_rankings_oc"
    
    @classmethod
    def __getattr__(cls, name: str):
        """Dynamic attribute access for configuration values (Python 3.7+)"""
        # Handle known configuration attributes
        config_map = {
            "ATHENA_DATABASE": ("ATHENA_DATABASE", cls._DEFAULTS["ATHENA_DATABASE"]),
            "ATHENA_SCHEMA": ("ATHENA_SCHEMA", cls._DEFAULTS["ATHENA_SCHEMA"]),
            "ATHENA_S3_OUTPUT_LOCATION": ("ATHENA_S3_OUTPUT_LOCATION", cls._DEFAULTS["ATHENA_S3_OUTPUT_LOCATION"]),
            "ATHENA_REGION": ("AWS_DEFAULT_REGION", cls._DEFAULTS["ATHENA_REGION"]),  # Check multiple env var names
            "DYNAMODB_REGION": ("AWS_DEFAULT_REGION", cls._DEFAULTS["DYNAMODB_REGION"]),
        }
        
        if name in config_map:
            # Check cache first
            if name not in cls._cache:
                config_key, default = config_map[name]
                # Special handling for region (check multiple env var names)
                if name in ("ATHENA_REGION", "DYNAMODB_REGION"):
                    region = (
                        _get_config_value("AWS_DEFAULT_REGION", "") or
                        _get_config_value("AWS_REGION", "") or
                        _get_config_value("REGION", "") or
                        default
                    )
                    cls._cache[name] = region
                else:
                    cls._cache[name] = _get_config_value(config_key, default)
            return cls._cache[name]
        
        raise AttributeError(f"'{cls.__name__}' has no attribute '{name}'")
    
    @classmethod
    def _clear_cache(cls):
        """Clear configuration cache (useful for testing or after config changes)"""
        cls._cache.clear()
    
    @classmethod
    def get_athena_client(cls) -> boto3.client:
        """Get configured Athena boto3 client"""
        return boto3.client('athena', region_name=cls.ATHENA_REGION)
    
    @classmethod
    def get_dynamodb_client(cls) -> boto3.client:
        """Get configured DynamoDB boto3 client"""
        return boto3.client('dynamodb', region_name=cls.DYNAMODB_REGION)
    
    @classmethod
    def get_dynamodb_resource(cls) -> boto3.resource:
        """Get configured DynamoDB boto3 resource (higher-level interface)"""
        return boto3.resource('dynamodb', region_name=cls.DYNAMODB_REGION)
    
    @classmethod
    def validate_aws_credentials(cls) -> tuple[bool, Optional[str]]:
        """
        Validate AWS credentials are configured
        
        Returns:
            (is_valid, error_message)
        """
        try:
            # Try to get AWS account ID using STS
            region = cls.ATHENA_REGION
            sts = boto3.client('sts', region_name=region)
            sts.get_caller_identity()
            return True, None
        except Exception as e:
            return False, f"AWS credentials not configured: {str(e)}"
    
    @classmethod
    def get_mart_table_name(cls, format_type: str) -> str:
        """
        Get the mart table name for the given format type
        
        Args:
            format_type: '50s' or 'oc'
            
        Returns:
            Table name
        """
        if format_type.lower() == '50s':
            return cls.MART_TABLE_50S
        elif format_type.lower() == 'oc':
            return cls.MART_TABLE_OC
        else:
            raise ValueError(f"Invalid format_type: {format_type}. Must be '50s' or 'oc'")
