#!/bin/bash

# Run script for Streamlit Draft Tool
# This ensures the Python path is set correctly

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to project root directory
cd "$SCRIPT_DIR"

# Check if virtual environment exists and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "⚠️  Warning: Virtual environment not found. Run ./setup.sh first."
    echo "   Continuing without virtual environment..."
fi

# Add project root to PYTHONPATH to ensure imports work
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Run Streamlit app
echo "Starting Streamlit app..."
streamlit run app/app.py
