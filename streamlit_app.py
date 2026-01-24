"""
Entry point for Streamlit Community Cloud

This file is a simple wrapper that redirects to the main app.
Streamlit Cloud looks for this file at the repository root by default.

Alternatively, you can configure Streamlit Cloud to use 'app/app.py' directly
as the main file path in your app settings.
"""

import sys
from pathlib import Path

# Add the app directory to the path so imports work correctly
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

# Execute the main app file
exec(open(app_dir / "app.py").read())
