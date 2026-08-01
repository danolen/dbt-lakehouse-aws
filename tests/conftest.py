import sys
from pathlib import Path

# The optimizer lives beside the Streamlit app, which imports it as a
# top-level module (`from lineup_optimizer import ...`). Mirror that here.
APP_DIR = Path(__file__).resolve().parents[1] / "apps" / "in-season-tool"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
