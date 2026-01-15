#!/usr/bin/env python3
"""
Setup verification script

This script checks that all dependencies and AWS configuration are set up correctly
before running the Streamlit app.
"""

import sys
import os

def check_python_version():
    """Check Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python 3.8+ required. You have Python {version.major}.{version.minor}")
        return False
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True

def check_dependencies():
    """Check required packages are installed"""
    required_packages = {
        'streamlit': 'streamlit',
        'boto3': 'boto3',
        'pandas': 'pandas',
        'numpy': 'numpy',
        'pyathena': 'pyathena'
    }
    
    missing = []
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"✅ {package_name} installed")
        except ImportError:
            print(f"❌ {package_name} not installed")
            missing.append(package_name)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False
    return True

def check_aws_credentials():
    """Check AWS credentials are configured"""
    try:
        import boto3
        sts = boto3.client('sts')
        identity = sts.get_caller_identity()
        print(f"✅ AWS credentials configured")
        print(f"   Account: {identity.get('Account', 'N/A')}")
        print(f"   User/Role: {identity.get('Arn', 'N/A').split('/')[-1]}")
        return True
    except Exception as e:
        print(f"❌ AWS credentials not configured: {str(e)}")
        print("   Run: aws configure")
        return False

def check_app_structure():
    """Check app directory structure"""
    required_files = [
        'app/app.py',
        'app/config/aws_config.py',
        'app/utils/database.py',
        'app/utils/dynamodb.py'
    ]
    
    all_exist = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} exists")
        else:
            print(f"❌ {file_path} missing")
            all_exist = False
    
    return all_exist

def main():
    """Run all checks"""
    print("🔍 Verifying Streamlit Draft Tool Setup...")
    print("=" * 50)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("App Structure", check_app_structure),
        ("AWS Credentials", check_aws_credentials),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 Checking {name}:")
        results.append((name, check_func()))
    
    print("\n" + "=" * 50)
    print("📊 Summary:")
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n🎉 All checks passed! You're ready to run the Streamlit app.")
        print("\n   Run: streamlit run app/app.py")
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above before running the app.")
        sys.exit(1)

if __name__ == "__main__":
    main()
